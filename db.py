import uuid

# Initialize product database
def init_product_db():
    return {
        'Sepatu Kulit': {
            'tasks': [
                {'id': 'SK1', 'name': 'Potong Sol', 'duration': 2, 'sequence': 1, 'attributes': {'cutting': 90, 'precision': 70, 'stamina': 60}, 'output_code': 'SOL-SK', 'requirements': []},
                {'id': 'SK2', 'name': 'Jahit Badan', 'duration': 3, 'sequence': 2, 'attributes': {'sewing': 85, 'precision': 80, 'stamina': 50}, 'output_code': 'BDN-SK', 'requirements': []},
                {'id': 'SK3', 'name': 'Tempel Sol & Badan', 'duration': 2, 'sequence': 3, 'attributes': {'gluing': 75, 'assembly': 70, 'stamina': 60}, 'output_code': 'ASM-SK', 'requirements': ['SOL-SK', 'BDN-SK']},
                {'id': 'SK4', 'name': 'Pasang Tali', 'duration': 1, 'sequence': 4, 'attributes': {'finishing': 60, 'precision': 65, 'stamina': 40}, 'output_code': 'FIN-SK', 'requirements': ['ASM-SK']},
                {'id': 'SK5', 'name': 'Quality Check', 'duration': 1, 'sequence': 5, 'attributes': {'inspection': 90, 'attention': 85, 'stamina': 30}, 'output_code': 'QC-SK', 'requirements': ['FIN-SK']}
            ]
        },
        'Sandal Eva': {
            'tasks': [
                {'id': 'SE1', 'name': 'Potong Eva Foam', 'duration': 1, 'sequence': 1, 'attributes': {'cutting': 85, 'precision': 65, 'stamina': 50}, 'output_code': 'EVA-SE', 'requirements': []},
                {'id': 'SE2', 'name': 'Cetak Mold', 'duration': 2, 'sequence': 2, 'attributes': {'molding': 90, 'precision': 70, 'stamina': 60}, 'output_code': 'MLD-SE', 'requirements': ['EVA-SE']},
                {'id': 'SE3', 'name': 'Pasang Tali', 'duration': 2, 'sequence': 3, 'attributes': {'assembly': 75, 'precision': 65, 'stamina': 45}, 'output_code': 'ASM-SE', 'requirements': ['MLD-SE']},
                {'id': 'SE4', 'name': 'Quality Check', 'duration': 1, 'sequence': 4, 'attributes': {'inspection': 85, 'attention': 80, 'stamina': 30}, 'output_code': 'QC-SE', 'requirements': ['ASM-SE']}
            ]
        },
        'Tas Wanita': {
            'tasks': [
                {'id': 'TW1', 'name': 'Potong Kain', 'duration': 2, 'sequence': 1, 'attributes': {'cutting': 80, 'precision': 75, 'stamina': 55}, 'output_code': 'KAI-TW', 'requirements': []},
                {'id': 'TW2', 'name': 'Jahit Badan Tas', 'duration': 4, 'sequence': 2, 'attributes': {'sewing': 90, 'precision': 85, 'stamina': 70}, 'output_code': 'BDN-TW', 'requirements': ['KAI-TW']},
                {'id': 'TW3', 'name': 'Pasang Aksesoris', 'duration': 2, 'sequence': 3, 'attributes': {'finishing': 75, 'precision': 80, 'stamina': 40}, 'output_code': 'AKS-TW', 'requirements': ['BDN-TW']},
                {'id': 'TW4', 'name': 'Quality Check', 'duration': 1, 'sequence': 4, 'attributes': {'inspection': 80, 'attention': 85, 'stamina': 30}, 'output_code': 'QC-TW', 'requirements': ['AKS-TW']}
            ]
        }
    }

# Initialize worker database
def init_worker_db():
    return {
        'W001': {
            'name': 'Ahmad',
            'skills': {'cutting': 90, 'precision': 75, 'stamina': 80, 'sewing': 50, 'gluing': 60, 'assembly': 65, 'finishing': 70, 'inspection': 60, 'molding': 40, 'attention': 75},
            'favorites': ['Sepatu Kulit', 'Tas Wanita', 'Sandal Eva'],
            'preference': 'fixed',  # fixed or flow
            'history': []
        },
        'W002': {
            'name': 'Budi',
            'skills': {'cutting': 60, 'precision': 80, 'stamina': 70, 'sewing': 90, 'gluing': 50, 'assembly': 55, 'finishing': 65, 'inspection': 70, 'molding': 30, 'attention': 85},
            'favorites': ['Tas Wanita', 'Sepatu Kulit', 'Sandal Eva'],
            'preference': 'flow',
            'history': []
        },
        'W003': {
            'name': 'Citra',
            'skills': {'cutting': 55, 'precision': 85, 'stamina': 60, 'sewing': 75, 'gluing': 65, 'assembly': 80, 'finishing': 85, 'inspection': 90, 'molding': 50, 'attention': 90},
            'favorites': ['Sandal Eva', 'Tas Wanita', 'Sepatu Kulit'],
            'preference': 'fixed',
            'history': []
        },
        'W004': {
            'name': 'Deni',
            'skills': {'cutting': 85, 'precision': 70, 'stamina': 90, 'sewing': 60, 'gluing': 85, 'assembly': 75, 'finishing': 70, 'inspection': 65, 'molding': 80, 'attention': 60},
            'favorites': ['Sepatu Kulit', 'Sandal Eva', 'Tas Wanita'],
            'preference': 'flow',
            'history': []
        }
    }

# Function to get all tasks for production orders
def get_all_tasks_for_production(orders, product_db):
    all_tasks = []
    
    for product, quantity in orders.items():
        if product in product_db:
            for _ in range(quantity):
                for task in product_db[product]['tasks']:
                    task_copy = task.copy()
                    task_copy['product'] = product
                    task_copy['instance_id'] = str(uuid.uuid4())[:8]
                    all_tasks.append(task_copy)
    
    return all_tasks