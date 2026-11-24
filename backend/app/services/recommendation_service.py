import re
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId

from app.core.logging import logger
from app.models.task_assignment import TaskAssignmentStatus, PerformanceLevel
from app.schemas.recommendation import EmployeeCandidateEvaluation, EmployeeRecommendationResult
from app.services.task_assignment_service import TaskAssignmentService
from app.services.performance_service import PerformanceCalculationService


class EmployeeRecommendationService:
    """
    Intelligent, deterministic & LLM-assisted employee recommendation engine for task assignment.
    
    1. Availability Analysis:
       - Uses actual Trello assignments & MongoDB task records.
       - Analyzes in-progress, pending, and overdue tasks.
       - Calculates remaining weekly/daily working capacity.
    2. Historical Work Analysis:
       - Completed tasks count, on-time completion rate, average duration, time variance.
       - Fairly marks insufficient data instead of assuming poor performance.
    3. Task Suitability:
       - Matches keywords in similar past tasks.
       - Verifies feasibility against upcoming deadlines.
       - Returns recommended employee, detailed metrics, and alternatives.
    """

    MAX_CONCURRENT_ACTIVE_TASKS = 5  # Standard capacity threshold for workload
    STANDARD_WORK_HOURS_PER_WEEK = 40.0
    ESTIMATED_HOURS_PER_ACTIVE_TASK = 8.0

    @classmethod
    async def get_all_eligible_employees(
        cls,
        db: AsyncIOMotorDatabase,
        board_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Collects all eligible employees from MongoDB users and Trello board members."""
        await TaskAssignmentService.reconcile_board_cards(db, board_id=board_id)

        users_cursor = db["users"].find({"is_active": True})
        users = await users_cursor.to_list(length=200)

        trello_members = []
        try:
            from app.mcp_server import trello_tools
            trello_res = await trello_tools.trello_list_board_members(board_id=board_id)
            trello_members = trello_res.get("members", [])
        except Exception as e:
            logger.warning(f"Failed to fetch live Trello members for recommendation: {e}")

        seen_names = set()
        employees = []

        for u in users:
            name = (u.get("full_name") or u.get("email") or "").strip()
            if not name:
                continue
            seen_names.add(name.lower())
            employees.append({
                "id": str(u["_id"]),
                "name": name,
                "email": u.get("email"),
                "role": u.get("role", "ADMIN"),
            })

        for tm in trello_members:
            tm_name = (tm.get("fullName") or tm.get("username") or "").strip()
            if tm_name and tm_name.lower() not in seen_names:
                seen_names.add(tm_name.lower())
                employees.append({
                    "id": str(tm.get("id")),
                    "name": tm_name,
                    "email": f"{tm.get('username', 'member')}@trello.board",
                    "role": "MEMBER",
                })

        return employees

    @classmethod
    async def evaluate_employee(
        cls,
        db: AsyncIOMotorDatabase,
        employee_id: str,
        employee_name: str,
        employee_email: Optional[str] = None,
        role: str = "MEMBER",
        task_name: Optional[str] = None,
        task_requirements: Optional[str] = None,
        due_date_str: Optional[str] = None,
        board_id: Optional[str] = None,
    ) -> EmployeeCandidateEvaluation:
        """Evaluates an individual employee's availability, historical performance, and suitability."""
        now = datetime.now(timezone.utc)

        # 1. Fetch all assigned/active tasks for this employee
        tasks = await TaskAssignmentService.get_employee_tasks(
            db=db,
            employee_id=employee_id,
            board_id=board_id,
        )

        assigned_tasks = [t for t in tasks if t.get("status") == TaskAssignmentStatus.ASSIGNED.value]
        in_progress_tasks = [t for t in tasks if t.get("status") == TaskAssignmentStatus.IN_PROGRESS.value]
        completed_tasks = [t for t in tasks if t.get("status") == TaskAssignmentStatus.COMPLETED.value]
        
        overdue_tasks = []
        for t in tasks:
            st = t.get("status")
            due = t.get("due_date")
            if st == TaskAssignmentStatus.OVERDUE.value:
                overdue_tasks.append(t)
            elif st in (TaskAssignmentStatus.ASSIGNED.value, TaskAssignmentStatus.IN_PROGRESS.value) and due:
                d_dt = due if due.tzinfo else due.replace(tzinfo=timezone.utc)
                if d_dt < now:
                    overdue_tasks.append(t)

        assigned_count = len(assigned_tasks)
        in_prog_count = len(in_progress_tasks)
        comp_count = len(completed_tasks)
        overdue_count = len(overdue_tasks)
        active_total = assigned_count + in_prog_count

        # Capacity & Workload score calculation
        estimated_committed_hours = active_total * cls.ESTIMATED_HOURS_PER_ACTIVE_TASK
        available_hours = max(0.0, round(cls.STANDARD_WORK_HOURS_PER_WEEK - estimated_committed_hours, 1))

        if active_total >= cls.MAX_CONCURRENT_ACTIVE_TASKS or overdue_count >= 3:
            workload_score = "OVERLOADED"
            has_capacity = False
        elif active_total >= 3 or overdue_count > 0:
            workload_score = "MODERATE"
            has_capacity = True
        else:
            workload_score = "OPTIMAL"
            has_capacity = True

        # 2. Historical performance from completed tasks
        perf = await PerformanceCalculationService.calculate_employee_performance(
            db=db,
            employee_id=employee_id,
            employee_name=employee_name,
        )

        on_time_rate = float(perf.get("on_time_rate") or 0.0)
        avg_act_dur = float(perf.get("average_actual_duration_minutes") or 0.0)
        avg_est_dur = float(perf.get("average_estimated_duration_minutes") or 0.0)
        perf_level = str(perf.get("level") or "NOT_ENOUGH_DATA")
        has_sufficient_history = (comp_count >= 2) and (perf_level != "NOT_ENOUGH_DATA")

        time_variance = round(avg_act_dur - avg_est_dur, 1)

        # 3. Similar Task Experience
        similar_count = 0
        search_terms = []
        if task_name:
            # tokenize task_name
            tokens = [t.lower() for t in re.findall(r"\b[a-zA-Z0-9_\-]{3,}\b", task_name)
                      if t.lower() not in ("task", "card", "the", "and", "for", "with", "new", "page")]
            search_terms.extend(tokens)
        if task_requirements:
            req_tokens = [t.lower() for t in re.findall(r"\b[a-zA-Z0-9_\-]{4,}\b", task_requirements)
                          if t.lower() not in ("please", "create", "implement", "update", "verify")]
            search_terms.extend(req_tokens)

        for ct in completed_tasks:
            c_title = str(ct.get("task_title", "")).lower()
            c_desc = str(ct.get("task_description", "")).lower()
            if any(term in c_title or term in c_desc for term in search_terms):
                similar_count += 1

        if similar_count >= 3:
            similar_exp = f"Extensive ({similar_count} completed tasks)"
        elif similar_count > 0:
            similar_exp = f"Moderate ({similar_count} completed task{'s' if similar_count > 1 else ''})"
        elif comp_count > 0:
            similar_exp = f"General Experience ({comp_count} completed tasks)"
        else:
            similar_exp = "No historical completed tasks recorded"

        # 4. Feasibility with deadline
        feasible = True
        if due_date_str:
            # If due date is very soon and employee has in-progress tasks or overdue tasks
            if (in_prog_count >= 2 or overdue_count > 0) and ("today" in due_date_str.lower() or "hour" in due_date_str.lower()):
                feasible = False

        # 5. Suitability Composite Score (0.0 - 100.0)
        # Weights:
        # - Capacity / Current Workload: 40 points
        # - On-time Completion & Reliability: 30 points
        # - Similar Task Experience: 20 points
        # - Feasibility / Overdue penalty: 10 points
        score = 0.0

        if workload_score == "OPTIMAL":
            score += 40.0 - (active_total * 4.0)
        elif workload_score == "MODERATE":
            score += 24.0 - (active_total * 2.0)
        else:
            score += 5.0  # Overloaded

        if has_sufficient_history:
            score += min(30.0, (on_time_rate / 100.0) * 30.0)
        else:
            # Fair baseline for new/insufficient employees (not penalizing them as bad)
            score += 18.0

        if similar_count >= 3:
            score += 20.0
        elif similar_count >= 1:
            score += 12.0
        elif comp_count > 0:
            score += 5.0
        else:
            score += 3.0

        if feasible:
            score += 10.0
        if overdue_count > 0:
            score = max(0.0, score - (overdue_count * 10.0))

        suitability_score = round(max(0.0, min(100.0, score)), 1)

        # Formulate Recommendation Reason
        reasons = []
        if workload_score == "OPTIMAL":
            reasons.append(f"Lowest active workload ({active_total} active task{'s' if active_total != 1 else ''}, {available_hours}h available capacity)")
        elif workload_score == "MODERATE":
            reasons.append(f"Manageable workload ({active_total} active tasks, {available_hours}h capacity)")
        else:
            reasons.append(f"High workload ({active_total} active tasks, {overdue_count} overdue)")

        if similar_count > 0:
            reasons.append(f"{similar_count} proven similar task{'s' if similar_count > 1 else ''} completed successfully")
        elif has_sufficient_history:
            reasons.append(f"{on_time_rate:.0f}% on-time completion record")
        else:
            reasons.append("Eligible collaborator (insufficient prior completion data)")

        if not feasible:
            reasons.append("Tight deadline risk given existing commitments")

        recommendation_reason = "; ".join(reasons) + "."

        return EmployeeCandidateEvaluation(
            employee_id=employee_id,
            employee_name=employee_name,
            employee_email=employee_email,
            role=role,
            current_workload_score=workload_score,
            assigned_tasks_count=assigned_count,
            in_progress_count=in_prog_count,
            pending_count=assigned_count,
            overdue_count=overdue_count,
            available_capacity_hours=available_hours,
            has_sufficient_capacity=has_capacity,
            completed_tasks_count=comp_count,
            on_time_completion_rate=on_time_rate,
            avg_actual_duration_minutes=avg_act_dur,
            avg_estimated_duration_minutes=avg_est_dur,
            time_variance_minutes=time_variance,
            has_sufficient_history=has_sufficient_history,
            performance_level=perf_level,
            similar_tasks_count=similar_count,
            similar_task_experience=similar_exp,
            estimated_task_completion_feasible=feasible,
            suitability_score=suitability_score,
            recommendation_reason=recommendation_reason,
        )

    @classmethod
    async def recommend_employee_for_task(
        cls,
        db: AsyncIOMotorDatabase,
        task_name: Optional[str] = None,
        task_requirements: Optional[str] = None,
        due_date_str: Optional[str] = None,
        target_employee_query: Optional[str] = None,
        board_id: Optional[str] = None,
    ) -> EmployeeRecommendationResult:
        """
        Calculates recommendation across all eligible employees on the board.
        If target_employee_query is specified (e.g. "Rahul has fewer tasks. Can he handle this task?"),
        specifically evaluates that employee and checks capacity/suitability.
        """
        all_emps = await cls.get_all_eligible_employees(db, board_id=board_id)
        if not all_emps:
            return EmployeeRecommendationResult(
                task_name=task_name,
                has_sufficient_capacity_overall=False,
                no_capacity_reason="No registered employees or active Trello board members found on this board.",
                explanation="No employees are currently available in the system for task assignment.",
            )

        evaluations: List[EmployeeCandidateEvaluation] = []
        for emp in all_emps:
            eval_res = await cls.evaluate_employee(
                db=db,
                employee_id=emp["id"],
                employee_name=emp["name"],
                employee_email=emp.get("email"),
                role=emp.get("role", "MEMBER"),
                task_name=task_name,
                task_requirements=task_requirements,
                due_date_str=due_date_str,
                board_id=board_id,
            )
            evaluations.append(eval_res)

        # If a specific target employee was queried by the Manager:
        # e.g., "Rahul has fewer tasks. Can he handle this task?"
        if target_employee_query:
            target_norm = target_employee_query.lower().strip()
            target_match = next((e for e in evaluations if target_norm in e.employee_name.lower()), None)
            if target_match:
                others = [e for e in evaluations if e.employee_id != target_match.employee_id]
                others.sort(key=lambda x: x.suitability_score, reverse=True)
                
                can_handle = target_match.has_sufficient_capacity and target_match.estimated_task_completion_feasible
                if can_handle:
                    exp = (
                        f"Yes, **{target_match.employee_name}** can handle this task! "
                        f"Current workload: {target_match.current_workload_score} ({target_match.in_progress_count + target_match.assigned_tasks_count} active tasks, "
                        f"{target_match.available_capacity_hours}h available capacity). {target_match.recommendation_reason}"
                    )
                else:
                    exp = (
                        f"**{target_match.employee_name}** currently has {target_match.current_workload_score} workload "
                        f"({target_match.overdue_count} overdue, {target_match.assigned_tasks_count + target_match.in_progress_count} active tasks) "
                        f"and may face difficulty completing this on time."
                    )
                
                return EmployeeRecommendationResult(
                    task_name=task_name,
                    task_requirements=task_requirements,
                    due_date=due_date_str,
                    target_employee_query=target_employee_query,
                    recommended_employee=target_match if can_handle else (others[0] if others and others[0].has_sufficient_capacity else None),
                    alternative_employees=others[:3],
                    has_sufficient_capacity_overall=any(e.has_sufficient_capacity for e in evaluations),
                    no_capacity_reason=None if any(e.has_sufficient_capacity for e in evaluations) else "All eligible employees are currently at capacity.",
                    explanation=exp,
                )

        # Standard Recommendation Flow:
        # Sort candidates primarily by capacity availability and suitability score
        capacity_candidates = [e for e in evaluations if e.has_sufficient_capacity]
        if not capacity_candidates:
            # No employee has sufficient capacity
            evaluations.sort(key=lambda x: x.assigned_tasks_count + x.in_progress_count)
            return EmployeeRecommendationResult(
                task_name=task_name,
                task_requirements=task_requirements,
                due_date=due_date_str,
                recommended_employee=None,
                alternative_employees=evaluations[:3],
                has_sufficient_capacity_overall=False,
                no_capacity_reason="All team members are currently operating at maximum capacity or have pending overdue tasks.",
                explanation="None of the employees currently have sufficient capacity to take on new tasks without risking deadlines.",
            )

        capacity_candidates.sort(key=lambda x: x.suitability_score, reverse=True)
        recommended = capacity_candidates[0]
        # Include other evaluated employees as alternatives (sorted by suitability)
        remaining = [e for e in evaluations if e.employee_id != recommended.employee_id]
        remaining.sort(key=lambda x: (x.has_sufficient_capacity, x.suitability_score), reverse=True)
        alternatives = remaining[:3]

        exp = (
            f"Based on real-time Trello workload analysis, **{recommended.employee_name}** is the most suitable employee. "
            f"They currently have an **{recommended.current_workload_score}** workload ({recommended.in_progress_count + recommended.assigned_tasks_count} active tasks, "
            f"{recommended.available_capacity_hours}h capacity) and {recommended.recommendation_reason}"
        )

        return EmployeeRecommendationResult(
            task_name=task_name,
            task_requirements=task_requirements,
            due_date=due_date_str,
            recommended_employee=recommended,
            alternative_employees=alternatives,
            has_sufficient_capacity_overall=True,
            no_capacity_reason=None,
            explanation=exp,
        )
