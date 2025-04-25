from datetime import datetime, timedelta
from db import get_all_tasks_for_production

def calculate_task_similarity(task1, task2):
    """Calculate similarity between two tasks based on their attributes"""
    similarity = 0
    common_attributes = 0
    
    for attr in task1['attributes']:
        if attr in task2['attributes']:
            similarity += 100 - abs(task1['attributes'][attr] - task2['attributes'][attr])
            common_attributes += 1
    
    if common_attributes == 0:
        return 0
    
    return similarity / common_attributes

def calculate_worker_task_match(worker, task):
    """Calculate match score between a worker and a task"""
    skill_score = 0
    relevant_skills = 0
    
    for attr in task['attributes']:
        if attr in worker['skills']:
            skill_score += worker['skills'][attr]
            relevant_skills += 1
    
    if relevant_skills == 0:
        return 0
    
    return skill_score / relevant_skills

def calculate_worker_role_score(worker, all_tasks):
    """Calculate if worker should be fixed or flow based on skills, motivation and preference"""
    # Extract the worker's preference weight
    preference_weight = 1 if worker['preference'] == 'fixed' else 0
    
    # Calculate average skill score across all tasks
    total_skill = 0
    for task_list in all_tasks.values():
        for task in task_list:
            total_skill += calculate_worker_task_match(worker, task)
    
    avg_skill = total_skill / sum(len(tasks) for tasks in all_tasks.values())
    
    # Calculate motivation based on favorites (simple approach)
    motivation = 0.5  # Neutral motivation
    
    # Calculate final score
    score = (avg_skill * 0.6) + (motivation * 0.2) + (preference_weight * 0.2)
    
    return score, 'fixed' if score > 70 else 'flow'

def check_prerequisites_met(completed_items, requirements):
    """Check if all prerequisites for a task have been met"""
    if not requirements:
        return True
    
    for req in requirements:
        if req not in completed_items:
            return False
    
    return True

def assign_roles_to_workers(workers, all_tasks_by_product):
    """Assign fixed or flow roles to workers based on their characteristics"""
    worker_roles = {}
    
    for worker_id, worker in workers.items():
        score, role = calculate_worker_role_score(worker, all_tasks_by_product)
        worker_roles[worker_id] = {
            'name': worker['name'],
            'assigned_role': role,
            'score': score
        }
    
    return worker_roles

def generate_schedule(orders, worker_availability, product_db, worker_db):
    """Generate the production schedule based on orders and worker availability"""
    # Filter workers based on availability
    available_workers = {worker_id: worker_db[worker_id] for worker_id in worker_availability if worker_id in worker_db}
    
    # No workers available
    if not available_workers:
        return {"error": "No workers available"}
    
    # No orders
    if not orders or sum(orders.values()) == 0:
        return {"error": "No orders to process"}
    
    # Get all tasks for the production run
    all_tasks = get_all_tasks_for_production(orders, product_db)
    
    # Group tasks by product
    all_tasks_by_product = {}
    for product in product_db:
        all_tasks_by_product[product] = [task for task in product_db[product]['tasks']]
    
    # Assign roles to workers (fixed or flow)
    worker_roles = assign_roles_to_workers(available_workers, all_tasks_by_product)
    
    # Sort tasks by sequence number and product
    sorted_tasks = sorted(all_tasks, key=lambda x: (x['sequence'], x['product']))
    
    # Initialize schedule data
    time_slots = 16  # 8 hours = 16 30-minute slots
    days_needed = max(1, len(sorted_tasks) // (len(available_workers) * time_slots) + 1)
    
    schedule = {}
    for worker_id in available_workers:
        schedule[worker_id] = []
        for day in range(days_needed):
            daily_slots = [None] * time_slots
            schedule[worker_id].append(daily_slots)
    
    # Track what's been completed
    completed_items = set()
    
    # Track which task instances are assigned
    assigned_tasks = set()
    
    # Calculate similarity between tasks
    task_similarity = {}
    for i, task1 in enumerate(sorted_tasks):
        task_key = f"{task1['product']}_{task1['id']}_{task1['instance_id']}"
        task_similarity[task_key] = {}
        for j, task2 in enumerate(sorted_tasks):
            if i != j:
                task2_key = f"{task2['product']}_{task2['id']}_{task2['instance_id']}"
                task_similarity[task_key][task2_key] = calculate_task_similarity(task1, task2)
    
    # Function to find best similar task for a worker
    def find_similar_task(current_task, worker_id, day, slot):
        current_task_key = f"{current_task['product']}_{current_task['id']}_{current_task['instance_id']}"
        best_score = -1
        best_task = None
        
        for task in sorted_tasks:
            task_key = f"{task['product']}_{task['id']}_{task['instance_id']}"
            
            # Skip if already assigned or prerequisites not met
            if (task_key in assigned_tasks or 
                not check_prerequisites_met(completed_items, task['requirements'])):
                continue
            
            # Calculate similarity score
            similarity = task_similarity.get(current_task_key, {}).get(task_key, 0)
            
            # Calculate worker match
            worker_match = calculate_worker_task_match(available_workers[worker_id], task)
            
            # Combined score
            score = (similarity * 0.7) + (worker_match * 0.3)
            
            if score > best_score:
                best_score = score
                best_task = task
        
        return best_task
    
    # Main scheduling algorithm
    for day in range(days_needed):
        for slot in range(time_slots):
            # Prioritize fixed workers first
            for worker_id, role_info in sorted(worker_roles.items(), 
                                               key=lambda x: 0 if x[1]['assigned_role'] == 'fixed' else 1):
                
                # Skip if already assigned for this slot
                if schedule[worker_id][day][slot] is not None:
                    continue
                
                # Find the best task for this worker
                best_task = None
                
                # For fixed workers, try to find tasks similar to their last assignment
                if role_info['assigned_role'] == 'fixed' and slot > 0:
                    last_slot = slot - 1
                    last_day = day
                    
                    # Look back to the previous day if needed
                    if last_slot < 0:
                        last_slot = time_slots - 1
                        last_day = day - 1
                    
                    # Only look back if we're not at the first day/slot
                    if last_day >= 0:
                        last_task = schedule[worker_id][last_day][last_slot]
                        if last_task and isinstance(last_task, dict):
                            best_task = find_similar_task(last_task, worker_id, day, slot)
                
                # If no similar task found, or for flow workers, find any available task
                if best_task is None:
                    for task in sorted_tasks:
                        task_key = f"{task['product']}_{task['id']}_{task['instance_id']}"
                        
                        # Skip if already assigned
                        if task_key in assigned_tasks:
                            continue
                        
                        # Check prerequisites
                        if check_prerequisites_met(completed_items, task['requirements']):
                            best_task = task
                            break
                
                # Assign task if found
                if best_task:
                    task_key = f"{best_task['product']}_{best_task['id']}_{best_task['instance_id']}"
                    assigned_tasks.add(task_key)
                    
                    # Calculate how many slots this task needs
                    slots_needed = best_task['duration']
                    
                    # Assign task to worker for required slots
                    for i in range(slots_needed):
                        current_slot = slot + i
                        current_day = day
                        
                        # Wrap to next day if needed
                        while current_slot >= time_slots:
                            current_slot -= time_slots
                            current_day += 1
                        
                        # Check if slot is available (could be already filled from previous iterations)
                        if current_day < days_needed and schedule[worker_id][current_day][current_slot] is None:
                            # Create a unique task instance for the schedule
                            task_instance = best_task.copy()
                            task_instance['status'] = 'in_progress' if i < slots_needed - 1 else 'completed'
                            task_instance['worker_role'] = role_info['assigned_role']
                            
                            schedule[worker_id][current_day][current_slot] = task_instance
                            
                            # Mark task as completed on the final slot
                            if i == slots_needed - 1:
                                completed_items.add(best_task['output_code'])
    
    # Rebalance - if a fixed worker has too many repetitive tasks and others are idle
    for day in range(days_needed):
        worker_task_counts = {}
        idle_workers = []
        
        # Count repeated tasks and find idle workers
        for worker_id in available_workers:
            worker_task_counts[worker_id] = {}
            idle_count = 0
            
            for slot in range(time_slots):
                task = schedule[worker_id][day][slot]
                if task:
                    task_id = task['id']
                    worker_task_counts[worker_id][task_id] = worker_task_counts[worker_id].get(task_id, 0) + 1
                else:
                    idle_count += 1
            
            if idle_count > time_slots // 2:  # If worker is idle for more than half the day
                idle_workers.append(worker_id)
        
        # Rebalance if there are fixed workers doing too many repetitive tasks
        for worker_id in worker_task_counts:
            if worker_roles[worker_id]['assigned_role'] == 'fixed':
                for task_id, count in worker_task_counts[worker_id].items():
                    if count > 8 and idle_workers:  # If a task is repeated more than half the day
                        # Find slots where this task is assigned
                        task_slots = []
                        for slot in range(time_slots):
                            task = schedule[worker_id][day][slot]
                            if task and task['id'] == task_id:
                                task_slots.append(slot)
                        
                        # Redistribute to idle workers
                        slots_to_redistribute = len(task_slots) - 8  # Keep 8 slots, redistribute the rest
                        slots_to_redistribute = min(slots_to_redistribute, len(idle_workers))
                        
                        for i in range(slots_to_redistribute):
                            idle_worker_id = idle_workers[i % len(idle_workers)]
                            slot_to_move = task_slots.pop()
                            
                            # Move the task and mark as rebalanced
                            task = schedule[worker_id][day][slot_to_move]
                            task['worker_role'] = 'rebalanced'
                            schedule[worker_id][day][slot_to_move] = None
                            
                            # Find an empty slot for the idle worker
                            for idle_slot in range(time_slots):
                                if schedule[idle_worker_id][day][idle_slot] is None:
                                    schedule[idle_worker_id][day][idle_slot] = task
                                    break
    
    # Convert schedule to a more readable format
    formatted_schedule = []
    
    for worker_id, days in schedule.items():
        worker_name = available_workers[worker_id]['name']
        role = worker_roles[worker_id]['assigned_role']
        
        for day_idx, slots in enumerate(days):
            for slot_idx, task in enumerate(slots):
                # Calculate time for this slot (8:00 AM start)
                hour = 8 + (slot_idx // 2)
                minute = (slot_idx % 2) * 30
                time_str = f"{hour:02d}:{minute:02d}"
                
                if task:
                    formatted_schedule.append({
                        "day": day_idx + 1,
                        "time": time_str,
                        "worker_id": worker_id,
                        "worker_name": worker_name,
                        "worker_role": role,
                        "task_role": task['worker_role'],
                        "product": task['product'],
                        "task_id": task['id'],
                        "task_name": task['name'],
                        "status": task['status']
                    })
                else:
                    formatted_schedule.append({
                        "day": day_idx + 1,
                        "time": time_str,
                        "worker_id": worker_id,
                        "worker_name": worker_name,
                        "worker_role": role,
                        "task_role": "idle",
                        "product": None,
                        "task_id": None,
                        "task_name": "IDLE",
                        "status": "idle"
                    })
    
    return {
        "schedule": formatted_schedule,
        "worker_roles": worker_roles,
        "completion_info": {
            "days_needed": days_needed,
            "completed_items": len(completed_items),
            "total_tasks": len(sorted_tasks)
        }
    }