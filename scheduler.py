from utils import (
    get_slot_from_time, 
    calculate_task_similarity, 
    calculate_worker_task_match, 
    calculate_worker_role_score, 
    check_prerequisites_met, 
    get_all_tasks_for_production
)

def generate_schedule(orders, worker_availability, product_db, worker_db):
    """Generate the production schedule based on orders and worker availability"""
    # Get all workers and their availability
    available_workers = {}
    for worker_id, availability in worker_availability.items():
        if worker_id in worker_db and availability['available']:
            available_workers[worker_id] = worker_db[worker_id].copy()
            available_workers[worker_id]['start_slot'] = get_slot_from_time(availability['start_time'])
    
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
        all_tasks_by_product[product] = product_db[product]
    
    # Assign roles to workers (fixed or flow)
    worker_roles = {}
    for worker_id, worker in available_workers.items():
        score, role = calculate_worker_role_score(worker, all_tasks_by_product)
        worker_roles[worker_id] = {
            'name': worker['name'],
            'assigned_role': role,
            'score': score
        }
    
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
            # Check worker availability for this slot
            for worker_id, worker in available_workers.items():
                # Skip if worker not available yet for this slot
                if worker['start_slot'] > slot:
                    continue
                
                # Skip if already assigned for this slot
                if schedule[worker_id][day][slot] is not None:
                    continue
                
                # Find the best task for this worker
                best_task = None
                
                # For fixed workers, try to find tasks similar to their last assignment
                if worker_roles[worker_id]['assigned_role'] == 'fixed' and slot > 0:
                    last_slot = slot - 1
                    last_day = day
                    
                    # Look back to the previous day if needed
                    if last_slot < 0:
                        last_slot = time_slots - 1
                        last_day = day - 1
                    
                    # Only look back if we're not at the first day/slot
                    if last_day >= 0 and last_slot >= available_workers[worker_id]['start_slot']:
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
                        
                        # Check if slot is available and within worker's available time
                        if (current_day < days_needed and 
                            current_slot >= available_workers[worker_id]['start_slot'] and
                            schedule[worker_id][current_day][current_slot] is None):
                            # Create a unique task instance for the schedule
                            task_instance = best_task.copy()
                            task_instance['status'] = 'in_progress' if i < slots_needed - 1 else 'completed'
                            task_instance['worker_role'] = worker_roles[worker_id]['assigned_role']
                            
                            schedule[worker_id][current_day][current_slot] = task_instance
                            
                            # Mark task as completed on the final slot
                            if i == slots_needed - 1:
                                completed_items.add(best_task['output_code'])
                        else:
                            # If we can't complete the task, break out and don't assign
                            break
    
    # Rebalance - if a fixed worker has too many repetitive tasks and others are idle
    # Apply the >32 slots rule (which means >8 30-minute slots in our system)
    for day in range(days_needed):
        worker_task_counts = {}
        idle_workers = []
        
        # Count repeated tasks and find idle workers
        for worker_id in available_workers:
            worker_task_counts[worker_id] = {}
            idle_count = 0
            
            for slot in range(time_slots):
                # Skip slots before worker's start time
                if slot < available_workers[worker_id]['start_slot']:
                    continue
                    
                task = schedule[worker_id][day][slot]
                if task:
                    task_id = task['id']
                    worker_task_counts[worker_id][task_id] = worker_task_counts[worker_id].get(task_id, 0) + 1
                else:
                    idle_count += 1
            
            if idle_count > (time_slots - available_workers[worker_id]['start_slot']) // 2:
                idle_workers.append(worker_id)
        
        # Rebalance if there are fixed workers doing too many repetitive tasks (>= 8 slots)
        for worker_id in worker_task_counts:
            if worker_roles[worker_id]['assigned_role'] == 'fixed':
                for task_id, count in worker_task_counts[worker_id].items():
                    if count > 8 and idle_workers:  # If a task is repeated more than 8 slots
                        # Find slots where this task is assigned
                        task_slots = []
                        for slot in range(time_slots):
                            if slot < available_workers[worker_id]['start_slot']:
                                continue
                                
                            task = schedule[worker_id][day][slot]
                            if task and task['id'] == task_id:
                                task_slots.append(slot)
                        
                        # Redistribute to idle workers
                        slots_to_redistribute = len(task_slots) - 8  # Keep 8 slots, redistribute the rest
                        slots_to_redistribute = min(slots_to_redistribute, len(idle_workers))
                        
                        for i in range(slots_to_redistribute):
                            idle_worker_id = idle_workers[i % len(idle_workers)]
                            
                            # Make sure we're not assigning to slots before worker's start time
                            valid_slots = [s for s in task_slots if s >= available_workers[idle_worker_id]['start_slot']]
                            if not valid_slots:
                                continue
                                
                            slot_to_move = valid_slots.pop()
                            task_slots.remove(slot_to_move)
                            
                            # Move the task and mark as rebalanced
                            task = schedule[worker_id][day][slot_to_move]
                            task['worker_role'] = 'rebalanced'
                            schedule[worker_id][day][slot_to_move] = None
                            
                            # Find an empty slot for the idle worker
                            for idle_slot in range(available_workers[idle_worker_id]['start_slot'], time_slots):
                                if schedule[idle_worker_id][day][idle_slot] is None:
                                    schedule[idle_worker_id][day][idle_slot] = task
                                    break
    
    # Convert schedule to a more readable format
    from utils import get_time_from_slot
    formatted_schedule = []
    
    for worker_id, days in schedule.items():
        worker_name = available_workers[worker_id]['name']
        role = worker_roles[worker_id]['assigned_role']
        
        for day_num, day_schedule in enumerate(days):
            for slot_num, task in enumerate(day_schedule):
                if task is not None:
                    formatted_schedule.append({
                        'worker_id': worker_id,
                        'worker_name': worker_name,
                        'assigned_role': task.get('worker_role', role),
                        'day': day_num + 1,
                        'time_slot': slot_num,
                        'start_time': get_time_from_slot(slot_num),
                        'end_time': get_time_from_slot(slot_num + task['duration']),
                        'product': task['product'],
                        'task_id': task['id'],
                        'task_name': task['name'],
                        'status': task['status']
                    })
    
    # Calculate production statistics
    production_stats = {
        'total_tasks_assigned': len(assigned_tasks),
        'total_tasks_needed': len(sorted_tasks),
        'completion_percentage': len(assigned_tasks) / len(sorted_tasks) * 100 if sorted_tasks else 0,
        'days_needed': days_needed,
        'workers_utilized': len(available_workers)
    }
    
    # Check for unassigned tasks
    unassigned_tasks = []
    for task in sorted_tasks:
        task_key = f"{task['product']}_{task['id']}_{task['instance_id']}"
        if task_key not in assigned_tasks:
            unassigned_tasks.append({
                'product': task['product'],
                'task_id': task['id'],
                'task_name': task['name'],
                'sequence': task['sequence'],
                'requirements': task['requirements']
            })
    
    return {
        'schedule': formatted_schedule,
        'worker_roles': worker_roles,
        'stats': production_stats,
        'unassigned_tasks': unassigned_tasks,
        'days_needed': days_needed
    }