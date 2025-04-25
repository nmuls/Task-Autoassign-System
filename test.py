import unittest
from db import init_product_db, init_worker_db, get_all_tasks_for_production
from system import (
    calculate_task_similarity,
    calculate_worker_task_match,
    calculate_worker_role_score,
    check_prerequisites_met,
    assign_roles_to_workers,
    generate_schedule
)

class TestTaskAssignSystem(unittest.TestCase):
    def setUp(self):
        self.product_db = init_product_db()
        self.worker_db = init_worker_db()
    
    def test_task_similarity(self):
        task1 = self.product_db['Sepatu Kulit']['tasks'][0]  # Potong Sol
        task2 = self.product_db['Sepatu Kulit']['tasks'][1]  # Jahit Badan
        
        similarity = calculate_task_similarity(task1, task2)
        self.assertIsInstance(similarity, float)
        self.assertGreaterEqual(similarity, 0)
        self.assertLessEqual(similarity, 100)
    
    def test_worker_task_match(self):
        worker = self.worker_db['W001']  # Ahmad
        task = self.product_db['Sepatu Kulit']['tasks'][0]  # Potong Sol
        
        match_score = calculate_worker_task_match(worker, task)
        self.assertIsInstance(match_score, float)
        self.assertGreaterEqual(match_score, 0)
        self.assertLessEqual(match_score, 100)
    
    def test_prerequisites_check(self):
        # Test with no prerequisites
        self.assertTrue(check_prerequisites_met(set(), []))
        
        # Test with prerequisites
        self.assertFalse(check_prerequisites_met(set(), ['SOL-SK']))
        self.assertTrue(check_prerequisites_met({'SOL-SK'}, ['SOL-SK']))
    
    def test_worker_role_assignment(self):
        workers = {
            'W001': self.worker_db['W001'],
            'W002': self.worker_db['W002']
        }
        
        roles = assign_roles_to_workers(workers, self.product_db)
        self.assertIsInstance(roles, dict)
        self.assertEqual(len(roles), 2)
        
        for worker_id, role_info in roles.items():
            self.assertIn('assigned_role', role_info)
            self.assertIn(role_info['assigned_role'], ['fixed', 'flow'])
    
    def test_schedule_generation(self):
        orders = {'Sepatu Kulit': 2}
        worker_availability = ['W001', 'W002']
        
        result = generate_schedule(orders, worker_availability, self.product_db, self.worker_db)
        
        self.assertIn('schedule', result)
        self.assertIn('worker_roles', result)
        self.assertIn('completion_info', result)
        
        # Check if any tasks were scheduled
        self.assertGreater(len(result['schedule']), 0)

if __name__ == '__main__':
    unittest.main()