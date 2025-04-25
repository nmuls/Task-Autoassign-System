import uuid

def init_product_db():
    """Initialize product database with sample products and their tasks"""
    return {
        'Standing Acrylic T': {
            'tasks': [
                {'id': 'ST1', 'name': 'Opening the masking paper', 'duration': 1, 'sequence': 1, 
                 'attributes': {'open_paper': 100, 'quality_control': 90, 'gluing': 50, 'bending': 30, 'assembling': 30, 'edge_scrap': 70}, 
                 'output_code': 'ST1-OUT', 'requirements': []},
                {'id': 'ST2', 'name': 'Unsharp/scrap the edge of the acrylic sheet', 'duration': 1, 'sequence': 2, 
                 'attributes': {'edge_scrap': 100, 'quality_control': 90, 'open_paper': 60, 'gluing': 45, 'bending': 20, 'assembling': 30}, 
                 'output_code': 'ST2-OUT', 'requirements': []},
                {'id': 'ST3', 'name': '1st step - top bending fold', 'duration': 1, 'sequence': 3, 
                 'attributes': {'bending': 100, 'gluing': 50, 'assembling': 40, 'quality_control': 40, 'open_paper': 20, 'edge_scrap': 20}, 
                 'output_code': 'ST3-OUT', 'requirements': ['ST1-OUT', 'ST2-OUT']},
                {'id': 'ST4', 'name': '2nd step - 1st foot side 90 degrees bending', 'duration': 1, 'sequence': 4, 
                 'attributes': {'bending': 100, 'quality_control': 40, 'open_paper': 40, 'gluing': 40, 'assembling': 30, 'edge_scrap': 10}, 
                 'output_code': 'ST4-OUT', 'requirements': ['ST3-OUT']},
                {'id': 'ST5', 'name': '3rd step - 2nd foot side 90 degrees bending', 'duration': 1, 'sequence': 5, 
                 'attributes': {'bending': 100, 'quality_control': 40, 'open_paper': 40, 'gluing': 40, 'assembling': 30, 'edge_scrap': 10}, 
                 'output_code': 'ST5-OUT', 'requirements': ['ST4-OUT']},
                {'id': 'ST6', 'name': 'QC-bending results and putting it in box', 'duration': 1, 'sequence': 6, 
                 'attributes': {'quality_control': 100, 'open_paper': 80, 'edge_scrap': 30, 'bending': 20, 'gluing': 10, 'assembling': 10}, 
                 'output_code': 'ST6-OUT', 'requirements': ['ST5-OUT']}
            ]
        },
        'Standing Acrylic L': {
            'tasks': [
                {'id': 'SL1', 'name': 'Opening the masking paper', 'duration': 1, 'sequence': 1, 
                 'attributes': {'open_paper': 100, 'quality_control': 90, 'gluing': 50, 'bending': 30, 'assembling': 30, 'edge_scrap': 70}, 
                 'output_code': 'SL1-OUT', 'requirements': []},
                {'id': 'SL2', 'name': 'Unsharp/scrap the edge of the acrylic sheet', 'duration': 1, 'sequence': 2, 
                 'attributes': {'edge_scrap': 100, 'quality_control': 90, 'open_paper': 60, 'gluing': 45, 'bending': 20, 'assembling': 30}, 
                 'output_code': 'SL2-OUT', 'requirements': []},
                {'id': 'SL3', 'name': '1st step - top bending fold', 'duration': 1, 'sequence': 3, 
                 'attributes': {'bending': 100, 'gluing': 50, 'assembling': 40, 'quality_control': 40, 'open_paper': 20, 'edge_scrap': 20}, 
                 'output_code': 'SL3-OUT', 'requirements': ['SL1-OUT', 'SL2-OUT']},
                {'id': 'SL4', 'name': '2nd step - 1st foot side 15 degrees bending', 'duration': 1, 'sequence': 4, 
                 'attributes': {'bending': 100, 'quality_control': 40, 'open_paper': 40, 'gluing': 40, 'assembling': 30, 'edge_scrap': 10}, 
                 'output_code': 'SL4-OUT', 'requirements': ['SL3-OUT']},
                {'id': 'SL5', 'name': 'QC-bending results and putting it in box', 'duration': 1, 'sequence': 5, 
                 'attributes': {'quality_control': 100, 'open_paper': 80, 'edge_scrap': 30, 'bending': 20, 'gluing': 10, 'assembling': 10}, 
                 'output_code': 'SL5-OUT', 'requirements': ['SL4-OUT']}
            ]
        }
    }

def init_worker_db():
    """Initialize worker database with sample workers and their skills"""
    return {
        'W001': {
            'id': 'W001',
            'name': 'John Smith',
            'skills': {
                'open_paper': 90,
                'quality_control': 85,
                'edge_scrap': 80,
                'bending': 75,
                'gluing': 70,
                'assembling': 65
            },
            'preference': 'fixed',
            'favorites': ['Standing Acrylic T', 'Standing Acrylic L'],
            'availability': True
        },
        'W002': {
            'id': 'W002',
            'name': 'Jane Doe',
            'skills': {
                'open_paper': 65,
                'quality_control': 95,
                'edge_scrap': 60,
                'bending': 90,
                'gluing': 85,
                'assembling': 80
            },
            'preference': 'flow',
            'favorites': ['Standing Acrylic L', 'Standing Acrylic T'],
            'availability': True
        },
        'W003': {
            'id': 'W003',
            'name': 'Mike Johnson',
            'skills': {
                'open_paper': 70,
                'quality_control': 75,
                'edge_scrap': 95,
                'bending': 65,
                'gluing': 90,
                'assembling': 85
            },
            'preference': 'fixed',
            'favorites': ['Standing Acrylic T'],
            'availability': True
        }
    }

def get_all_tasks_for_production(orders, product_db):
    """Generate all tasks needed for the production orders"""
    all_tasks = []
    
    for product, quantity in orders.items():
        if product in product_db and quantity > 0:
            for i in range(quantity):
                instance_id = i + 1
                for task in product_db[product]['tasks']:
                    task_copy = task.copy()
                    task_copy['product'] = product
                    task_copy['instance_id'] = instance_id
                    task_copy['output_code'] = f"{task['output_code']}-{instance_id}"
                    
                    # Adjust requirements to include instance ID
                    updated_requirements = []
                    for req in task['requirements']:
                        updated_requirements.append(f"{req}-{instance_id}")
                    task_copy['requirements'] = updated_requirements
                    
                    all_tasks.append(task_copy)
    
    return all_tasks