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
            skill_score += worker['skills'][attr] * (task['attributes'][attr] / 100)
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
    task_count = 0
    
    for task_list in all_tasks.values():
        for task in task_list:
            total_skill += calculate_worker_task_match(worker, task)
            task_count += 1
    
    avg_skill = total_skill / task_count if task_count > 0 else 0
    
    # Calculate motivation based on favorites
    motivation = 0.5  # Neutral motivation
    if hasattr(worker, 'favorites') and len(worker['favorites']) > 0:
        motivation = 0.8  # Higher motivation if worker has preferences
    
    # Calculate final score
    score = (avg_skill * 0.6) + (motivation * 0.2) + (preference_weight * 0.2)
    
    return score * 100, 'fixed' if score > 0.7 else 'flow'

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

def generate_schedule(orders, worker_availability, product_db, worker_db, rebalance_threshold=16):
    """Generate the production schedule based on orders and worker availability"""
    # Filter workers based on availability
    available_workers = {worker_id: worker_db[worker_id] for worker_id, info in worker_availability.items() 
                      if info['available'] and worker_id in worker_db}
    
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
        all_tasks_by_product[product] = product_db[product]['tasks']
    
    # Assign roles to workers (fixed or flow)
    worker_roles = assign_roles_to_workers(available_workers, all_tasks_by_product)
    
    # Sort tasks by sequence number and product
    sorted_tasks = sorted(all_tasks, key=lambda x: (x['sequence'], x['product']))
    
    # Initialize schedule data
    time_slots = 16  # 8 hours = 16 30-minute slots
    days_needed = max(1, len(sorted_tasks) // (len(available_workers) * time_slots) + 1)
    
    # Initialize schedule for each worker
    schedule = {}
    for worker_id in available_workers:
        schedule[worker_id] = [None] * (days_needed * time_slots)
    
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
    def find_similar_task(current_task, worker_id):
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
    formatted_schedule = []
    
    for day in range(days_needed):
        for slot in range(time_slots):
            # Calculate absolute slot index
            abs_slot = day * time_slots + slot
            
            # Check worker availability for this slot
            available_for_slot = {}
            for worker_id, info in worker_availability.items():
                # Worker is available if:
                # 1. They are marked as available
                # 2. Their start slot is less than or equal to current slot
                if info['available'] and info['start_slot'] <= slot and worker_id in worker_db:
                    available_for_slot[worker_id] = worker_db[worker_id]
            
            # Skip if no workers available for this slot
            if not available_for_slot:
                continue
            
            # Prioritize fixed workers first
            for worker_id, role_info in sorted(worker_roles.items(), 
                                               key=lambda x: 0 if x[1]['assigned_role'] == 'fixed' else 1):
                
                # Skip if worker is not available for this slot
                if worker_id not in available_for_slot:
                    continue
                
                # Skip if already assigned for this slot
                if schedule[worker_id][abs_slot] is not None:
                    continue
                
                # Find the best task for this worker
                best_task = None
                
                # For fixed workers, try to find tasks similar to their last assignment
                if role_info['assigned_role'] == 'fixed' and abs_slot > 0:
                    # Find the most recent task assigned to this worker
                    for prev_slot in range(abs_slot-1, -1, -1):
                        last_task = schedule[worker_id][prev_slot]
                        if last_task and isinstance(last_task, dict):
                            best_task = find_similar_task(last_task, worker_id)
                            break
                
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
                    
                    # Check if we have enough consecutive slots
                    consecutive_free = 0
                    for i in range(slots_needed):
                        check_slot = abs_slot + i
                        if check_slot < len(schedule[worker_id]) and schedule[worker_id][check_slot] is None:
                            consecutive_free += 1
                        else:
                            break
                    
                    # Only assign if we have enough consecutive slots
                    if consecutive_free >= slots_needed:
                        # Assign task to worker for required slots
                        for i in range(slots_needed):
                            current_slot = abs_slot + i
                            
                            # Create a unique task instance for the schedule
                            task_instance = best_task.copy()
                            task_instance['status'] = 'in_progress' if i < slots_needed - 1 else 'completed'
                            task_instance['worker_role'] = role_info['assigned_role']
                            
                            schedule[worker_id][current_slot] = task_instance
                            
                            # Calculate time for this slot (8:00 AM start)
                            slot_of_day = current_slot % time_slots
                            day_num = current_slot // time_slots
                            hour = 8 + (slot_of_day // 2)
                            minute = (slot_of_day % 2) * 30
                            time_str = f"{hour:02d}:{minute:02d}"
                            
                            # Add to formatted schedule
                            formatted_schedule.append({
                                "day": day_num + 1,
                                "time": time_str,
                                "worker_id": worker_id,
                                "worker_name": available_workers[worker_id]['name'],
                                "worker_role": role_info['assigned_role'],
                                "task_role": task_instance['worker_role'],
                                "product": task_instance['product'],
                                "task_id": task_instance['id'],
                                "task_name": task_instance['name'],
                                "status": task_instance['status']
                            })
                            
                            # Mark task as completed on the final slot
                            if i == slots_needed - 1:
                                completed_items.add(best_task['output_code'])
    
    # Add idle slots to the formatted schedule
    for worker_id in available_workers:
        worker_name = available_workers[worker_id]['name']
        role = worker_roles[worker_id]['assigned_role']
        
        for abs_slot in range(len(schedule[worker_id])):
            if schedule[worker_id][abs_slot] is None:
                # Calculate time and day for this slot
                slot_of_day = abs_slot % time_slots
                day_num = abs_slot // time_slots
                
                # Skip if worker is not available for this slot based on start time
                if worker_availability[worker_id]['start_slot'] > slot_of_day:
                    continue
                
                hour = 8 + (slot_of_day // 2)
                minute = (slot_of_day % 2) * 30
                time_str = f"{hour:02d}:{minute:02d}"
                
                formatted_schedule.append({
                    "day": day_num + 1,
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
    
    # Sort formatted schedule by day, time, and worker
    formatted_schedule.sort(key=lambda x: (x["day"], x["time"], x["worker_id"]))
    
    return {
        "schedule": formatted_schedule,
        "worker_roles": worker_roles,
        "completion_info": {
            "days_needed": days_needed,
            "completed_items": len(completed_items),
            "total_tasks": len(sorted_tasks)
        }
    }