from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings
from app.core.logging import logger
from app.models.task_assignment import PerformanceLevel, TaskAssignmentStatus


class PerformanceCalculationService:
    """
    Deterministic, backend-only scoring service for employee performance classification.
    Adheres strictly to the specification: LLMs do NOT calculate performance levels.
    """

    @classmethod
    async def calculate_employee_performance(
        cls,
        db: AsyncIOMotorDatabase,
        employee_id: str,
        employee_name: Optional[str] = None,
        evaluation_days: Optional[int] = None,
    ) -> Dict[str, Any]:
        eval_days = evaluation_days or settings.PERFORMANCE_EVALUATION_DAYS
        now = datetime.now(timezone.utc)
        cutoff_date = now - timedelta(days=eval_days)

        # 1. Fetch relevant tasks in rolling window (matching by employee_id or name)
        emp_match: List[Dict[str, Any]] = [{"employee_id": str(employee_id)}]
        if employee_name:
            emp_match.append({"employee_name": employee_name})
        try:
            from bson import ObjectId
            u = await db["users"].find_one({"_id": ObjectId(employee_id)})
            if u:
                if u.get("full_name") and u.get("full_name") != employee_name:
                    emp_match.append({"employee_name": u["full_name"]})
                if u.get("email"):
                    emp_match.append({"employee_email": u["email"]})
                employee_name = employee_name or u.get("full_name")
        except Exception:
            pass

        query = {
            "$and": [
                {"$or": emp_match},
                {"status": {"$ne": TaskAssignmentStatus.CANCELLED.value}},
                {
                    "$or": [
                        {"created_at": {"$gte": cutoff_date}},
                        {"completed_at": {"$gte": cutoff_date}},
                        {"status": {"$in": [TaskAssignmentStatus.ASSIGNED.value, TaskAssignmentStatus.IN_PROGRESS.value, TaskAssignmentStatus.OVERDUE.value]}}
                    ]
                }
            ]
        }
        cursor = db["task_assignments"].find(query)
        tasks = await cursor.to_list(length=1000)

        total_assigned = len(tasks)
        completed_tasks = [t for t in tasks if t.get("status") == TaskAssignmentStatus.COMPLETED.value]
        in_progress_tasks = [t for t in tasks if t.get("status") == TaskAssignmentStatus.IN_PROGRESS.value]
        overdue_tasks = []
        for t in tasks:
            status = t.get("status")
            due = t.get("due_date")
            if status == TaskAssignmentStatus.OVERDUE.value:
                overdue_tasks.append(t)
            elif status in (TaskAssignmentStatus.ASSIGNED.value, TaskAssignmentStatus.IN_PROGRESS.value) and due:
                due_dt = due if due.tzinfo else due.replace(tzinfo=timezone.utc)
                if due_dt < now:
                    overdue_tasks.append(t)

        completed_count = len(completed_tasks)
        in_progress_count = len(in_progress_tasks)
        overdue_count = len(overdue_tasks)

        # Calculate average estimated vs actual duration
        est_durations = [t.get("estimated_duration_minutes") for t in completed_tasks if t.get("estimated_duration_minutes") is not None]
        act_durations = [t.get("actual_duration_minutes") for t in completed_tasks if t.get("actual_duration_minutes") is not None]
        avg_estimated = round(sum(est_durations) / len(est_durations), 1) if est_durations else 0.0
        avg_actual = round(sum(act_durations) / len(act_durations), 1) if act_durations else 0.0

        # Check sufficiency: require at least PERFORMANCE_MIN_COMPLETED_TASKS completed tasks
        min_required = settings.PERFORMANCE_MIN_COMPLETED_TASKS
        if completed_count < min_required:
            level = PerformanceLevel.NOT_ENOUGH_DATA.value
            overall_score = 0.0
            on_time_rate = 0.0
            consistency_score = 0.0
            completion_rate = round((completed_count / total_assigned * 100.0), 1) if total_assigned > 0 else 0.0
            reliability_score = 0.0
            reason = f"Insufficient historical completed tasks ({completed_count}/{min_required} required in {eval_days}-day window)."
        else:
            # Metric 1: On-time completion rate (40% weight)
            # Tasks completed on or before due date
            tasks_with_due = [t for t in completed_tasks if t.get("due_date")]
            if tasks_with_due:
                on_time_count = 0
                for t in tasks_with_due:
                    comp_dt = t.get("completed_at")
                    due_dt = t.get("due_date")
                    if comp_dt and due_dt:
                        c_dt = comp_dt if comp_dt.tzinfo else comp_dt.replace(tzinfo=timezone.utc)
                        d_dt = due_dt if due_dt.tzinfo else due_dt.replace(tzinfo=timezone.utc)
                        if c_dt <= d_dt:
                            on_time_count += 1
                    else:
                        on_time_count += 1
                on_time_rate = round((on_time_count / len(tasks_with_due)) * 100.0, 1)
            else:
                on_time_rate = 100.0

            # Metric 2: Estimated vs actual duration consistency (30% weight)
            # Consistency score based on variance
            consistency_scores = []
            for t in completed_tasks:
                est = t.get("estimated_duration_minutes")
                act = t.get("actual_duration_minutes")
                if est is not None and est > 0 and act is not None:
                    if act <= est:
                        consistency_scores.append(100.0)
                    else:
                        overrun_ratio = (act - est) / est
                        score = max(0.0, 100.0 * (1.0 - overrun_ratio))
                        consistency_scores.append(score)
            if consistency_scores:
                consistency_score = round(sum(consistency_scores) / len(consistency_scores), 1)
            else:
                consistency_score = 100.0

            # Metric 3: Task completion rate (20% weight)
            denominator = completed_count + in_progress_count + overdue_count
            completion_rate = round((completed_count / denominator * 100.0), 1) if denominator > 0 else 100.0

            # Metric 4: Deadline reliability (10% weight)
            # Penalized if due date is repeatedly pushed back / changed
            task_ids = [str(t.get("_id") or t.get("id")) for t in tasks]
            if task_ids:
                changes_cursor = db["task_assignment_history"].find({
                    "assignment_id": {"$in": task_ids},
                    "action": "due_date_updated"
                })
                change_logs = await changes_cursor.to_list(length=1000)
                changes_per_task: Dict[str, int] = {}
                for log in change_logs:
                    aid = str(log.get("assignment_id"))
                    changes_per_task[aid] = changes_per_task.get(aid, 0) + 1

                rel_scores = []
                for tid in task_ids:
                    changes = changes_per_task.get(tid, 0)
                    # Deduct 20 points per deadline change
                    task_rel = max(0.0, 100.0 - (changes * 20.0))
                    rel_scores.append(task_rel)
                reliability_score = round(sum(rel_scores) / len(rel_scores), 1) if rel_scores else 100.0
            else:
                reliability_score = 100.0

            # Compute weighted overall score
            w_ontime = settings.PERFORMANCE_WEIGHT_ON_TIME
            w_consist = settings.PERFORMANCE_WEIGHT_CONSISTENCY
            w_complete = settings.PERFORMANCE_WEIGHT_COMPLETION
            w_rel = settings.PERFORMANCE_WEIGHT_RELIABILITY

            overall_score = round(
                (on_time_rate * w_ontime)
                + (consistency_score * w_consist)
                + (completion_rate * w_complete)
                + (reliability_score * w_rel),
                1
            )
            # Clamp to 0-100
            overall_score = max(0.0, min(100.0, overall_score))

            if overall_score >= settings.PERFORMANCE_HIGH_THRESHOLD:
                level = PerformanceLevel.HIGH.value
            elif overall_score >= settings.PERFORMANCE_MEDIUM_THRESHOLD:
                level = PerformanceLevel.MEDIUM.value
            else:
                level = PerformanceLevel.LOW.value

            reason = (
                f"Evaluation score {overall_score}/100 across {completed_count} completed tasks "
                f"in {eval_days}-day rolling window (On-Time: {on_time_rate}%, "
                f"Consistency: {consistency_score}%, Completion: {completion_rate}%, Reliability: {reliability_score}%)."
            )

        # 2. Check previous performance to track level transitions
        prev_perf = await db["employee_performance"].find_one({"employee_id": str(employee_id)})
        old_level = prev_perf.get("level") if prev_perf else None

        if old_level != level:
            # Record level history entry
            level_entry = {
                "employee_id": str(employee_id),
                "old_level": old_level,
                "new_level": level,
                "score": overall_score,
                "reason": reason,
                "calculated_at": now,
            }
            await db["employee_level_history"].insert_one(level_entry)
            logger.info(f"Employee {employee_id} performance level transitioned from {old_level} to {level} (Score: {overall_score})")

        # 3. Upsert snapshot into employee_performance collection
        perf_doc = {
            "employee_id": str(employee_id),
            "employee_name": employee_name or (prev_perf.get("employee_name") if prev_perf else None),
            "level": level,
            "overall_score": overall_score,
            "on_time_rate": on_time_rate,
            "consistency_score": consistency_score,
            "completion_rate": completion_rate,
            "reliability_score": reliability_score,
            "completed_tasks_count": completed_count,
            "total_assigned_tasks_count": total_assigned,
            "in_progress_tasks_count": in_progress_count,
            "overdue_tasks_count": overdue_count,
            "avg_estimated_minutes": avg_estimated,
            "avg_actual_minutes": avg_actual,
            "rolling_days": eval_days,
            "reason": reason,
            "calculated_at": now,
        }

        await db["employee_performance"].update_one(
            {"employee_id": str(employee_id)},
            {"$set": perf_doc},
            upsert=True
        )

        return perf_doc

