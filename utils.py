import uuid

def get_slot_from_time(time_str):
    """Convert time string (HH:MM) to slot number (0-15)"""
    hours, minutes = map(int, time_str.split(':'))
    return (hours - 8) * 2 + (1 if minutes >= 30 else 0)

def get_time_from_slot(slot):
    """Convert slot number (0-15) to time string (HH:MM)"""
    hour = 8 + (slot // 2)
    minute = (slot % 2) * 30
    return f"{hour:02d}:{minute:02d}"

def get_all_time_slots():
    """Get all available time slots from 8:00 to 16:00"""
    return [get_time_from_slot(i) for i in range(16)]

def calculate_task_similarity(task1, task2):
    """Calculate similarity between two tasks based on their attributes"""
    similarity = 0
    common_attributes = 0

    for attr in task1['Attributes']:
        if attr in task2['Attributes']:
            similarity += 100 - abs(task1['Attributes'][attr] - task2['Attributes'][attr])
            common_attributes += 1

    if common_attributes == 0:
        return 0

    return similarity / common_attributes

def calculate_worker_task_match(worker, task):
    """Calculate match score between a worker and a task"""
    if not worker or not task:
        return 0

    skill_score = 0
    relevant_skills = 0

    for attr in task['Attributes']:
        if attr in worker['skills']:
            skill_score += worker['skills'][attr]
            relevant_skills += 1

    if relevant_skills == 0:
        return 0

    return skill_score / relevant_skills

def calculate_worker_role_score(worker, all_tasks):
    """
    Calculate if worker should be fixed or flow based on skills, 
    motivation and preference
    """
    preference_weight = 1 if worker['preference'] == 'fixed' else 0

    total_skill = 0
    task_count = 0
    for product, product_info in all_tasks.items():
        tasks = product_info.get('tasks', [])
        for task in tasks:
            total_skill += calculate_worker_task_match(worker, task)
            task_count += 1

    avg_skill = total_skill / task_count if task_count > 0 else 0

    motivation = 0.5  # Default neutral motivation

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

def get_all_tasks_for_production(orders, product_db):
    """Get all tasks needed for a production run"""
    all_tasks = []

    for product, quantity in orders.items():
        if product in product_db and quantity > 0:
            for _ in range(quantity):
                for task in product_db[product]['tasks']:
                    task_copy = task.copy()
                    task_copy['product'] = product
                    task_copy['instance_id'] = str(uuid.uuid4())[:8]
                    all_tasks.append(task_copy)

    return all_tasks

def format_time_for_display(slot_index, slot_duration_minutes=30, start_hour=8):
    """Convert slot index to human-readable time like 08:00, 08:30, etc."""
    total_minutes = slot_index * slot_duration_minutes
    hour = start_hour + (total_minutes // 60)
    minute = total_minutes % 60
    return f"{hour:02d}:{minute:02d}"
