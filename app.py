import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
from collections import defaultdict
import time
import io
import base64

# Set page configuration
st.set_page_config(
    page_title="Task Auto-Assignment System",
    page_icon="📋",
    layout="wide"
)

# Cache data loading to improve performance
@st.cache_data
def load_data():
    workers_df = pd.read_csv("workers.csv")
    products_df = pd.read_csv("products.csv")
    return workers_df, products_df

# Load data
workers_df, products_df = load_data()

# Create unique product list
unique_products = products_df['Product'].unique()

# Sidebar for navigation
st.sidebar.title("Navigation")
page = st.sidebar.radio("Go to", ["Home", "Product Database", "Worker Database", "Production Order", "About"])

# Custom CSS styling
st.markdown("""
<style>
    .main-header {
        font-size: 36px;
        font-weight: bold;
        color: #1E88E5;
        margin-bottom: 20px;
    }
    .sub-header {
        font-size: 24px;
        font-weight: bold;
        color: #424242;
        margin-bottom: 10px;
        margin-top: 20px;
    }
    .task-card {
        background-color: #f0f2f6;
        border-radius: 5px;
        padding: 10px;
        margin-bottom: 10px;
    }
    .fixed-role {
        background-color: #e3f2fd;
        border-left: 5px solid #1976D2;
        padding: 5px;
    }
    .flow-role {
        background-color: #e8f5e9;
        border-left: 5px solid #43A047;
        padding: 5px;
    }
    .highlight {
        background-color: #fff8e1;
        border-left: 5px solid #FFB300;
        padding: 5px;
    }
</style>
""", unsafe_allow_html=True)

def calculate_skill_match(worker_skills, task_attributes):
    """Calculate skill match score between worker and task"""
    skill_score = 0
    total_weight = 0
    
    for skill in ['Bending', 'Gluing', 'Assembling', 'EdgeScrap', 'OpenPaper', 'QualityControl']:
        if task_attributes[skill] > 0:  # Only consider relevant skills for this task
            weight = task_attributes[skill] / 100  # Convert percentage to decimal
            skill_score += worker_skills[skill] * weight
            total_weight += weight
    
    # Avoid division by zero
    if total_weight == 0:
        return 0
        
    return skill_score / total_weight

def generate_time_slots(start_hour=8, end_hour=16):
    """Generate 30-minute time slots between given hours"""
    slots = []
    for hour in range(start_hour, end_hour):
        slots.append(f"{hour:02d}:00")
        slots.append(f"{hour:02d}:30")
    return slots

def check_requirements_met(semifinished_inventory, requirements, quantity_needed=1):
    """Check if all requirement tasks have sufficient inventory"""
    if not requirements or pd.isna(requirements):
        return True
        
    required_tasks = [req.strip() for req in str(requirements).split(',')]
    for req in required_tasks:
        if req not in semifinished_inventory or semifinished_inventory[req] < quantity_needed:
            return False
    return True

def calculate_required_days(products_to_produce, workers_df, products_df):
    """Calculate approximately how many days will be needed to complete all tasks"""
    # Count total task slots needed
    total_task_slots = 0
    for product, quantity in products_to_produce.items():
        product_tasks = products_df[products_df['Product'] == product]
        for _, task in product_tasks.iterrows():
            total_task_slots += task['DurationSlot'] * quantity
    
    # Calculate worker slots available per day
    num_workers = len(workers_df)
    time_slots = generate_time_slots(8, 16)
    worker_slots_per_day = num_workers * len(time_slots)
    
    # Calculate days needed with 30% buffer for dependencies and constraints
    estimated_days = total_task_slots / worker_slots_per_day
    days_with_buffer = int(np.ceil(estimated_days * 1.3))
    
    # Ensure at least 1 day, and cap at a reasonable maximum
    return max(1, min(days_with_buffer, 10))

def calculate_batch_size(task1_time, task2_time, workers_task1, workers_task2, safety_factor=1.2):
    """Calculate buffer batch size to prevent following task from overtaking"""
    if task2_time >= task1_time:  # If next task is slower, no need for buffer
        return 1
    
    # If next task is faster, calculate buffer
    rate1 = task1_time / workers_task1  # Time per piece for task 1
    rate2 = task2_time / workers_task2  # Time per piece for task 2
    
    # If task2 is faster than task1, we need buffer
    if rate1 > rate2:
        buffer_factor = safety_factor * (rate1 / rate2)
        return max(int(buffer_factor), 1)
    return 1

def get_worker_task_efficiency(worker_data, task):
    """Calculate how efficient a worker would be at a specific task"""
    # Calculate skill match
    skill_score = calculate_skill_match(
        {
            'Bending': worker_data['skills']['Bending'],
            'Gluing': worker_data['skills']['Gluing'],
            'Assembling': worker_data['skills']['Assembling'],
            'EdgeScrap': worker_data['skills']['EdgeScrap'],
            'OpenPaper': worker_data['skills']['OpenPaper'],
            'QualityControl': worker_data['skills']['QualityControl']
        },
        {
            'Bending': task.get('bending', 0),
            'Gluing': task.get('gluing', 0),
            'Assembling': task.get('assembling', 0),
            'EdgeScrap': task.get('edge_scrap', 0),
            'OpenPaper': task.get('open_paper', 0),
            'QualityControl': task.get('quality_control', 0)
        }
    )
    
    # Product preference
    product_pref = 0
    product = task.get('product')
    if product == worker_data['product_preferences'][0]:
        product_pref = 0.2
    elif product == worker_data['product_preferences'][1]:
        product_pref = 0.1
    elif product == worker_data['product_preferences'][2]:
        product_pref = 0.05
    
    # Task continuity bonus (if worker did this task before)
    continuity_bonus = 0.15 if task.get('task_id') in worker_data.get('recent_tasks', []) else 0
    
    return skill_score * 0.7 + product_pref + continuity_bonus

def assign_tasks_improved(products_to_produce, workers_df, products_df, days=None):
    """Improved algorithm to assign tasks to workers based on skills, continuity and flow"""
    # Auto-calculate days if not specified
    if days is None:
        days = calculate_required_days(products_to_produce, workers_df, products_df)
    
    time_slots = generate_time_slots(8, 16)
    total_slots = len(time_slots)
    
    # Create multi-day schedule
    schedule = {}
    for day in range(1, days + 1):
        schedule[day] = {worker: {slot: None for slot in time_slots} for worker in workers_df['Worker']}
    
    # Track semi-finished inventory across days
    semifinished_inventory = defaultdict(int)
    
    # Keep track of worker states and history
    worker_states = {}
    for _, worker in workers_df.iterrows():
        worker_name = worker['Worker']
        worker_states[worker_name] = {
            'current_task': None,
            'task_sequence': [],
            'recent_tasks': set(),  # Store recent tasks to promote continuity
            'completed_products': defaultdict(int),
            'flow_preference': worker['FlowPreference'],
            'fixed_tasks': set(),  # Tasks this worker specializes in
            'skills': {
                'Bending': worker['Bending'],
                'Gluing': worker['Gluing'],
                'Assembling': worker['Assembling'],
                'EdgeScrap': worker['EdgeScrap'],
                'OpenPaper': worker['OpenPaper'],
                'QualityControl': worker['QualityControl']
            },
            'product_preferences': [worker['FavoriteProduct1'], worker['FavoriteProduct2'], worker['FavoriteProduct3']]
        }
    
    # Build complete task database with dependencies and details
    task_database = {}
    product_tasks = {}
    
    for product, quantity in products_to_produce.items():
        product_df = products_df[products_df['Product'] == product]
        
        if product not in product_tasks:
            product_tasks[product] = []
        
        # Sort tasks by dependency order
        tasks_to_process = []
        processed_tasks = set()
        
        # First, collect all tasks with no requirements
        for _, task_row in product_df.iterrows():
            task_id = task_row['Result']
            requirements = task_row['Requirements'] if not pd.isna(task_row['Requirements']) else ""
            
            task_database[task_id] = {
                'product': product,
                'task_name': task_row['Task'],
                'duration': task_row['DurationSlot'],
                'requirements': requirements,
                'bending': task_row['Bending'],
                'gluing': task_row['Gluing'],
                'assembling': task_row['Assembling'],
                'edge_scrap': task_row['EdgeScrap'],
                'open_paper': task_row['OpenPaper'],
                'quality_control': task_row['QualityControl'],
                'total_needed': quantity,
                'completed': 0
            }
            
            if not requirements or pd.isna(requirements):
                tasks_to_process.append(task_id)
                product_tasks[product].append(task_id)
        
        # Then process tasks with requirements
        while tasks_to_process:
            task_id = tasks_to_process.pop(0)
            processed_tasks.add(task_id)
            
            # Find tasks that depend on this one
            for _, task_row in product_df.iterrows():
                next_task_id = task_row['Result']
                if next_task_id in processed_tasks:
                    continue
                
                requirements = task_row['Requirements'] if not pd.isna(task_row['Requirements']) else ""
                if not requirements:
                    continue
                
                required_tasks = [req.strip() for req in str(requirements).split(',')]
                
                # Check if all required tasks are processed
                if all(req in processed_tasks for req in required_tasks):
                    tasks_to_process.append(next_task_id)
                    product_tasks[product].append(next_task_id)
    
    # Function to find the best task for a worker at the current time
    def find_best_task_for_worker(worker_name, day, slot_idx, remaining_slots, worker_role):
        worker_data = workers_df[workers_df['Worker'] == worker_name].iloc[0]
        worker_state = worker_states[worker_name]
        
        # Check if worker is continuing a task
        if worker_state['current_task']:
            return worker_state['current_task']
        
        best_task = None
        best_score = -1
        
        # Determine eligible tasks based on inventory and requirements
        eligible_tasks = []
        
        for product, quantity in products_to_produce.items():
            for task_id in product_tasks[product]:
                task = task_database[task_id]
                
                # Skip if all needed quantity is completed
                if task['completed'] >= task['total_needed']:
                    continue
                
                # Check if requirements are met based on inventory
                requirements = task['requirements']
                requirements_met = check_requirements_met(semifinished_inventory, requirements, 1)
                
                if requirements_met:
                    eligible_tasks.append({
                        'task_id': task_id,
                        'product': product,
                        'task_name': task['task_name'],
                        'duration': task['duration'],
                        'bending': task['bending'],
                        'gluing': task['gluing'],
                        'assembling': task['assembling'],
                        'edge_scrap': task['edge_scrap'],
                        'open_paper': task['open_paper'],
                        'quality_control': task['quality_control'],
                        'requirements': requirements
                    })
        
        if not eligible_tasks:
            return None
        
        # For fixed-role workers, prioritize tasks they've done before
        if worker_role == 'fixed':
            # First priority: continue with fixed tasks
            for task in eligible_tasks:
                if task['task_id'] in worker_state['fixed_tasks']:
                    task_score = get_worker_task_efficiency(worker_state, task) + 0.5  # Bonus for fixed task
                    if task_score > best_score and task['duration'] <= remaining_slots:
                        best_score = task_score
                        best_task = task
            
            # If no fixed task was found, maybe assign a new fixed task
            if not best_task and len(worker_state['fixed_tasks']) < 2:
                for task in eligible_tasks:
                    task_score = get_worker_task_efficiency(worker_state, task)
                    if task_score > best_score and task['duration'] <= remaining_slots:
                        best_score = task_score
                        best_task = task
        
        # For flow-role workers, prioritize task flow
        else:  # flow role
            # Check if worker is in the middle of a product flow
            current_product = None
            if worker_state['task_sequence']:
                last_task = worker_state['task_sequence'][-1]
                current_product = last_task.get('product')
            
            for task in eligible_tasks:
                # Continuity bonus for same product
                continuity_bonus = 0.3 if current_product and task['product'] == current_product else 0
                
                # Calculate efficiency score
                task_score = get_worker_task_efficiency(worker_state, task) + continuity_bonus
                
                # Only consider tasks that fit in remaining time slots
                if task['duration'] <= remaining_slots and task_score > best_score:
                    best_score = task_score
                    best_task = task
        
        # If we found a best task, update fixed tasks set if appropriate
        if best_task and worker_role == 'fixed':
            worker_state['fixed_tasks'].add(best_task['task_id'])
        
        return best_task
    
    # Process each day in the schedule
    for day in range(1, days + 1):
        # For each time slot
        for slot_idx, time_slot in enumerate(time_slots):
            # Get available workers
            available_workers = [worker for worker in workers_df['Worker'] 
                                if schedule[day][worker][time_slot] is None]
            
            if not available_workers:
                continue
            
            # Assign tasks starting with workers who have higher role tendency
            # First determine worker roles based on preferences
            worker_roles = {}
            for worker_name in available_workers:
                worker_state = worker_states[worker_name]
                # Higher preference value means worker prefers flow role
                worker_roles[worker_name] = 'flow' if worker_state['flow_preference'] >= 0.6 else 'fixed'
            
            # Sort workers by role (fixed first, then flow)
            sorted_workers = sorted(available_workers, 
                                   key=lambda w: (0 if worker_roles[w] == 'fixed' else 1))
            
            # Process each available worker
            for worker_name in sorted_workers:
                # Skip if worker is already assigned for this slot
                if schedule[day][worker_name][time_slot] is not None:
                    continue
                
                worker_role = worker_roles[worker_name]
                remaining_slots = total_slots - slot_idx
                
                # Find best task for this worker
                best_task = find_best_task_for_worker(
                    worker_name, day, slot_idx, remaining_slots, worker_role
                )
                
                if best_task:
                    task_id = best_task['task_id']
                    task_duration = best_task['duration']
                    
                    # Check if task fits in remaining slots
                    if task_duration <= remaining_slots:
                        # Assign task for its duration
                        batch_size = 5  # Default batch size for task assignment
                        
                        # Create task info
                        task_info = {
                            'product': best_task['product'],
                            'task': best_task['task_name'],
                            'task_id': task_id,
                            'role': worker_role,
                            'batch': batch_size
                        }
                        
                        # Assign the task for its duration
                        for i in range(int(task_duration)):
                            if slot_idx + i < total_slots:
                                current_slot = time_slots[slot_idx + i]
                                schedule[day][worker_name][current_slot] = task_info
                        
                        # Update worker state
                        worker_states[worker_name]['current_task'] = best_task
                        worker_states[worker_name]['recent_tasks'].add(task_id)
                        worker_states[worker_name]['task_sequence'].append(best_task)
                        
                        # Update task completion
                        task_database[task_id]['completed'] += batch_size
                        
                        # Update semifinished inventory
                        semifinished_inventory[task_id] += batch_size
                        
                        # If task has requirements, consume those from inventory
                        requirements = best_task['requirements']
                        if requirements and not pd.isna(requirements):
                            required_tasks = [req.strip() for req in str(requirements).split(',')]
                            for req in required_tasks:
                                semifinished_inventory[req] = max(0, semifinished_inventory[req] - batch_size)
                        
                        # After the task duration, reset current_task
                        if slot_idx + task_duration < total_slots:
                            worker_states[worker_name]['current_task'] = None
                    
            # After assigning tasks to workers in this time slot, 
            # check if any task is falling behind and adjust priorities
            
            # Calculate production rates and identify bottlenecks
            task_production_rates = defaultdict(int)
            workers_per_task = defaultdict(int)
            
            # Count workers assigned to each task
            for worker_name in workers_df['Worker']:
                if schedule[day][worker_name][time_slot] is not None:
                    task_id = schedule[day][worker_name][time_slot]['task_id']
                    workers_per_task[task_id] += 1
            
            # Adjust priorities for next assignments based on bottlenecks
            for task_id, task_data in task_database.items():
                if task_data['completed'] < task_data['total_needed'] and workers_per_task[task_id] == 0:
                    # No workers on this task, check if it's a bottleneck
                    if check_requirements_met(semifinished_inventory, task_data['requirements']):
                        # This is a task that could be worked on but has no workers
                        # Prioritize it for next assignments
                        pass
    
    # Calculate metrics for schedule evaluation
    total_tasks_planned = sum(task['total_needed'] for task in task_database.values())
    total_tasks_completed = sum(task['completed'] for task in task_database.values())
    completion_percentage = (total_tasks_completed / total_tasks_planned * 100) if total_tasks_planned > 0 else 0
    
    # Collect metrics by day and product
    tasks_by_day = {}
    for day in range(1, days + 1):
        day_tasks = 0
        for worker in workers_df['Worker']:
            for slot in time_slots:
                if schedule[day][worker][slot] is not None:
                    day_tasks += 1
        tasks_by_day[day] = day_tasks // 2  # Divide by average task duration
    
    # Collect worker metrics
    worker_metrics = {}
    for worker in workers_df['Worker']:
        role_count = {'fixed': 0, 'flow': 0}
        tasks_completed = 0
        products_worked = set()
        task_switches = 0
        last_task = None
        
        for day in range(1, days + 1):
            for slot in time_slots:
                task_info = schedule[day][worker][slot]
                if task_info is not None:
                    tasks_completed += 1
                    products_worked.add(task_info['product'])
                    role_count[task_info['role']] += 1
                    
                    if last_task is not None and last_task != task_info['task_id']:
                        task_switches += 1
                    
                    last_task = task_info['task_id']
        
        worker_metrics[worker] = {
            'role_distribution': role_count,
            'tasks_completed': tasks_completed,
            'products_worked': len(products_worked),
            'task_switches': task_switches
        }
    
    completion_stats = {
        'total_tasks': total_tasks_planned,
        'completed_tasks': total_tasks_completed,
        'completion_percentage': completion_percentage,
        'tasks_by_day': tasks_by_day,
        'semifinished_inventory': dict(semifinished_inventory),
        'worker_metrics': worker_metrics
    }
    
    return schedule, completion_stats, worker_states, worker_roles, days

def get_table_download_link(df, filename, text):
    """Generate a link to download the dataframe as a CSV file"""
    csv = df.to_csv(index=False)
    b64 = base64.b64encode(csv.encode()).decode()
    href = f'<a href="data:file/csv;base64,{b64}" download="{filename}" style="color:blue;">{text}</a>'
    return href

# Main app logic
if page == "Home":
    st.markdown('<div class="main-header">Task Auto-Assignment System</div>', unsafe_allow_html=True)
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown("""
        ### Welcome to the Task Auto-Assignment System
        
        This system helps optimize production scheduling by:
        
        1. Grouping similar tasks across different products
        2. Matching workers to tasks based on skills
        3. Balancing fixed and flow roles for maximum efficiency
        4. Respecting task requirements and dependencies
        
        Use the navigation panel on the left to explore different sections of the application.
        """)
    
    with col2:
        st.image("https://cdn.pixabay.com/photo/2018/03/10/12/00/teamwork-3213924_1280.jpg", width=300)
    
    st.markdown("""
    ### How it works
    
    1. *Product Database*: View and manage products and their production tasks
    2. *Worker Database*: Manage worker profiles and their skill attributes
    3. *Production Order*: Create production orders and generate optimized schedules
    
    Get started by navigating to the *Production Order* page to create your first optimized schedule.
    """)

elif page == "Product Database":
    st.markdown('<div class="main-header">Product Database</div>', unsafe_allow_html=True)
    
    # Display product list
    st.markdown('<div class="sub-header">Products</div>', unsafe_allow_html=True)
    
    # Group products and show their tasks
    for product in unique_products:
        with st.expander(f"{product}"):
            product_tasks = products_df[products_df['Product'] == product]
            st.dataframe(product_tasks)
            
            # Create a flow diagram of tasks
            task_graph = alt.Chart(product_tasks).mark_circle(size=200).encode(
                x=alt.X('Task:N', sort=None, title='Task Sequence'),
                y=alt.Y('Product:N', title=None),
                color=alt.Color('Result:N', legend=None),
                tooltip=['Task', 'Result', 'Requirements']
            ).properties(
                width=600,
                height=100
            )
            
            # Add connecting lines based on requirements
            edges = []
            for _, task in product_tasks.iterrows():
                if not pd.isna(task['Requirements']):
                    requirements = task['Requirements'].split(', ')
                    for req in requirements:
                        edges.append({
                            'source': req,
                            'target': task['Result']
                        })
            
            if edges:
                edges_df = pd.DataFrame(edges)
                lines = alt.Chart(edges_df).mark_line(color='gray').encode(
                    x='source:N',
                    x2='target:N',
                    y='source:N',
                    y2='target:N'
                )
                st.altair_chart(task_graph + lines)
            else:
                st.altair_chart(task_graph)
            
    # Show skill attribute distribution
    st.markdown('<div class="sub-header">Task Attribute Distribution</div>', unsafe_allow_html=True)
    
    # Create attribute comparison chart
    chart_data = products_df.melt(
        id_vars=['Product', 'Task', 'Result'], 
        value_vars=['Bending', 'Gluing', 'Assembling', 'EdgeScrap', 'OpenPaper', 'QualityControl'],
        var_name='Attribute', value_name='Score'
    )
    
    attribute_chart = alt.Chart(chart_data).mark_bar().encode(
        x=alt.X('Attribute:N', title='Task Attribute'),
        y=alt.Y('mean(Score):Q', title='Average Score'),
        color='Attribute:N',
        column='Product:N'
    ).properties(
        width=100,
        height=200
    )
    
    st.altair_chart(attribute_chart)

elif page == "Worker Database":
    st.markdown('<div class="main-header">Worker Database</div>', unsafe_allow_html=True)
    
    # Display workers and their skills
    st.markdown('<div class="sub-header">Workers</div>', unsafe_allow_html=True)
    
    workers_display = workers_df.copy()
    
    for _, worker in workers_df.iterrows():
        with st.expander(f"{worker['Worker']}"):
            col1, col2 = st.columns([3, 2])
            
            with col1:
                # Display worker skills
                skills = ['Bending', 'Gluing', 'Assembling', 'EdgeScrap', 'OpenPaper', 'QualityControl']
                skill_data = pd.DataFrame({
                    'Skill': skills,
                    'Score': [worker[skill] for skill in skills]
                })
                
                chart = alt.Chart(skill_data).mark_bar().encode(
                    x=alt.X('Score:Q', scale=alt.Scale(domain=[0, 1])),
                    y=alt.Y('Skill:N', sort='-x'),
                    color=alt.Color('Score:Q', scale=alt.Scale(scheme='blues'))
                ).properties(
                    width=400,
                    height=200,
                    title=f"{worker['Worker']} Skills"
                )
                
                st.altair_chart(chart)
            
            with col2:
                # Display worker preferences
                st.write("*Flow/Fixed Preference:*")
                pref_chart = alt.Chart(pd.DataFrame({
                    'Type': ['Flow', 'Fixed'],
                    'Score': [worker['FlowPreference'], 1 - worker['FlowPreference']]
                })).mark_bar().encode(
                    x='Type:N',
                    y='Score:Q',
                    color='Type:N'
                ).properties(
                    width=200,
                    height=150
                )
                
                st.altair_chart(pref_chart)
                
                st.write("*Product Preferences:*")
                st.write(f"1. {worker['FavoriteProduct1']}")
                st.write(f"2. {worker['FavoriteProduct2']}")
                st.write(f"3. {worker['FavoriteProduct3']}")

elif page == "Production Order":
    st.markdown('<div class="main-header">Production Order</div>', unsafe_allow_html=True)
    
    st.markdown("""
    ### Create a production order to generate an optimized schedule
    
    Select products and quantities, then customize parameters to generate an optimized work schedule.
    Production days will be automatically calculated based on your order size and worker availability.
    """)
    
    # Create form for production order
    with st.form("production_order"):
        # Product selection
        st.markdown('<div class="sub-header">Select Products</div>', unsafe_allow_html=True)
        
        # Create columns for product selection
        product_cols = st.columns(3)
        product_quantities = {}
        
        for i, product in enumerate(unique_products):
            col_idx = i % 3
            with product_cols[col_idx]:
                quantity = st.number_input(f"{product}", min_value=0, value=0, step=1)
                if quantity > 0:
                    product_quantities[product] = quantity
        
        # Schedule parameters
        st.markdown('<div class="sub-header">Schedule Parameters</div>', unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        
        with col1:
            worker_allocation = st.slider("Worker Role Balance (Flow vs Fixed)", 
                                         min_value=0, max_value=100, value=50,
                                         help="0 = All Flow, 100 = All Fixed")
        
        with col2:
            prioritize = st.selectbox("Prioritize", 
                                     ["Balanced", "Worker Skills", "Product Grouping", "Task Flow"])
            worker_availability = st.multiselect("Available Workers", 
                                               options=workers_df['Worker'].tolist(),
                                               default=workers_df['Worker'].tolist())
        
        # Submit button
        submitted = st.form_submit_button("Generate Schedule")
    
    # Process form submission
    if submitted:
        if not product_quantities:
            st.warning("Please select at least one product with a quantity greater than 0.")
            st.stop()
        
        if not worker_availability:
            st.warning("Please select at least one available worker.")
            st.stop()
        
        # Filter workers based on availability
        available_workers_df = workers_df[workers_df['Worker'].isin(worker_availability)]
        
        # Display loading spinner
        with st.spinner("Generating optimized schedule..."):
            # Calculate days needed for this order
            days_needed = calculate_required_days(product_quantities, available_workers_df, products_df)
            
            # Generate the schedule
            schedule, stats, worker_states, worker_roles, days = assign_tasks_improved(
                product_quantities, 
                available_workers_df, 
                products_df, 
                days=days_needed
            )
            
            st.success(f"Schedule generated successfully for {days} days!")
            
            # Display completion statistics
            st.markdown('<div class="sub-header">Production Overview</div>', unsafe_allow_html=True)
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("Completion Rate", f"{stats['completion_percentage']:.1f}%")
            
            with col2:
                st.metric("Planned Tasks", stats['total_tasks'])
            
            with col3:
                st.metric("Completed Tasks", stats['completed_tasks'])
            
            # Tasks by day chart
            tasks_by_day_df = pd.DataFrame({
                'Day': list(stats['tasks_by_day'].keys()),
                'Tasks': list(stats['tasks_by_day'].values())
            })
            
            day_chart = alt.Chart(tasks_by_day_df).mark_bar().encode(
                x='Day:O',
                y='Tasks:Q',
                color=alt.value('#1976D2')
            ).properties(
                title='Tasks Completed by Day',
                width=600,
                height=300
            )
            
            st.altair_chart(day_chart)
            
            # Display worker roles
            st.markdown('<div class="sub-header">Worker Role Assignment</div>', unsafe_allow_html=True)
            
            role_data = []
            for worker, role in worker_roles.items():
                role_data.append({
                    'Worker': worker,
                    'Role': role
                })
            
            role_df = pd.DataFrame(role_data)
            
            # Add CSS class for styling
            styled_roles = role_df.style.apply(
                lambda x: ['background-color: #e3f2fd' if x['Role'] == 'fixed' else 'background-color: #e8f5e9' for _ in x],
                axis=1
            )
            
            st.dataframe(styled_roles)
            
                # Display daily schedule
    st.markdown('<div class="sub-header">Daily Schedules</div>', unsafe_allow_html=True)

    # Create tabs for each day
    day_tabs = st.tabs([f"Day {day}" for day in range(1, days + 1)])
    time_slots = generate_time_slots(8, 16)

    # Create a list of worker names for column headers
    worker_names = available_workers_df['Worker'].tolist()

    for day_idx, day_tab in enumerate(day_tabs):
        day = day_idx + 1
        
        with day_tab:
            # Prepare data for this day's schedule
            day_data = []
            
            for worker in worker_names:
                worker_role = worker_roles[worker]
                role_class = "fixed-role" if worker_role == "fixed" else "flow-role"
                
                for slot in time_slots:
                    task_info = schedule[day][worker][slot]
                    
                    if task_info is not None:
                        day_data.append({
                            'Worker': worker,
                            'Time': slot,
                            'Product': task_info['product'],
                            'Task': task_info['task'],
                            'Role': worker_role,
                            'RoleClass': role_class
                        })
            
            if day_data:
                day_df = pd.DataFrame(day_data).drop_duplicates()
                
                # Generate schedule chart
                schedule_chart = alt.Chart(day_df).mark_rect().encode(
                    x=alt.X('Time:O', title='Time Slot', sort=time_slots),
                    y=alt.Y('Worker:N', title='Worker'),
                    color=alt.Color('Product:N', legend=alt.Legend(title="Product")),
                    tooltip=['Worker', 'Time', 'Product', 'Task', 'Role']
                ).properties(
                    width=800,
                    height=400,
                    title=f"Day {day} Schedule"
                )
                
                text_chart = alt.Chart(day_df).mark_text().encode(
                    x=alt.X('Time:O', sort=time_slots),
                    y='Worker:N',
                    text='Task:N',
                    color=alt.value('black')
                )
                
                st.altair_chart(schedule_chart + text_chart)
                
                # Display schedule as table
                st.markdown(f"#### Day {day} Task Assignment")
                
                # NEW CODE: Pivot table with workers as columns and time slots as rows
                # This is the reverse of the original pivoting
                pivot_df = day_df.pivot_table(
                    index='Time', 
                    columns='Worker', 
                    values='Task', 
                    aggfunc='first'
                ).reset_index().fillna('')
                
                # Generate HTML with worker names as column headers
                html_table = "<table style='width:100%; border-collapse: collapse;'>"
                html_table += "<tr><th>Time Slot</th>"  # First column is time slot
                
                for worker in worker_names:
                    role = worker_roles.get(worker, 'flow')
                    role_class = "fixed-role" if role == "fixed" else "flow-role"
                    html_table += f"<th class='{role_class}'>{worker}</th>"  # Worker names as headers
                
                html_table += "</tr>"
                
                for _, row in pivot_df.iterrows():
                    time_slot = row['Time']
                    
                    html_table += f"<tr><td>{time_slot}</td>"  # Time slot in first column
                    
                    for worker in worker_names:
                        cell_value = row.get(worker, '')
                        if cell_value:
                            # Find product for this task
                            product_data = day_df[(day_df['Worker'] == worker) & 
                                                (day_df['Time'] == time_slot)]
                            
                            if not product_data.empty:
                                product = product_data['Product'].values[0]
                                role = worker_roles.get(worker, 'flow')
                                role_class = "fixed-role" if role == "fixed" else "flow-role"
                                html_table += f"<td class='{role_class}'>{cell_value}<br><small>({product})</small></td>"
                            else:
                                html_table += f"<td></td>"
                        else:
                            html_table += f"<td></td>"
                    
                    html_table += "</tr>"
                
                html_table += "</table>"
                
                st.markdown(html_table, unsafe_allow_html=True)
            else:
                st.info(f"No tasks scheduled for Day {day}")
            
            # Worker performance metrics
            st.markdown('<div class="sub-header">Worker Performance Metrics</div>', unsafe_allow_html=True)
            
            # Convert worker metrics to DataFrame for visualization
            worker_metrics_data = []
            for worker, metrics in stats['worker_metrics'].items():
                worker_metrics_data.append({
                    'Worker': worker,
                    'Role': worker_roles.get(worker, 'flow'),
                    'Tasks Completed': metrics['tasks_completed'],
                    'Products Worked': metrics['products_worked'],
                    'Task Switches': metrics['task_switches'],
                    'Fixed Role Tasks': metrics['role_distribution']['fixed'],
                    'Flow Role Tasks': metrics['role_distribution']['flow']
                })
            
            metrics_df = pd.DataFrame(worker_metrics_data)
            
            # Display worker metrics table
            st.dataframe(metrics_df)
            
            # Create worker performance chart
            metrics_chart = alt.Chart(metrics_df).mark_bar().encode(
                x='Worker:N',
                y='Tasks Completed:Q',
                color='Role:N',
                tooltip=['Worker', 'Tasks Completed', 'Products Worked', 'Task Switches']
            ).properties(
                width=600,
                height=300,
                title='Worker Performance'
            )
            
            st.altair_chart(metrics_chart)
            
            # Export options
            st.markdown('<div class="sub-header">Export Options</div>', unsafe_allow_html=True)
            
            # Convert schedule to DataFrame for export
            export_data = []
            for day in range(1, days + 1):
                for worker in available_workers_df['Worker']:
                    for slot in time_slots:
                        task_info = schedule[day][worker][slot]
                        if task_info is not None:
                            export_data.append({
                                'Day': day,
                                'Worker': worker,
                                'Time': slot,
                                'Product': task_info['product'],
                                'Task': task_info['task'],
                                'Role': task_info['role']
                            })
            
            if export_data:
                export_df = pd.DataFrame(export_data).drop_duplicates()
                
                # Provide download link
                st.markdown(get_table_download_link(export_df, 
                                                  'production_schedule.csv', 
                                                  '📥 Download Production Schedule'), 
                          unsafe_allow_html=True)
                
                # Also provide worker metrics for download
                st.markdown(get_table_download_link(metrics_df, 
                                                  'worker_metrics.csv', 
                                                  '📥 Download Worker Metrics'), 
                          unsafe_allow_html=True)

elif page == "About":
    st.markdown('<div class="main-header">About</div>', unsafe_allow_html=True)
    
    st.markdown("""
    ## Task Auto-Assignment System
    
    This application optimizes production scheduling by assigning workers to tasks based on their skills,
    preferences, and the demands of the production order. It aims to balance between fixed-role and flow-role
    assignments to maximize efficiency while maintaining worker satisfaction.
    
    ### Key Features
    
    - **Skill-Based Assignment**: Workers are assigned to tasks based on their skill levels
    - **Flow vs. Fixed Roles**: Balances between specialization and flexibility
    - **Product-Based Continuity**: Groups related tasks for better flow
    - **Task Dependency Management**: Respects required sequences and dependencies
    - **Multi-Day Scheduling**: Optimizes across multiple production days
    
    ### How the Algorithm Works
    
    1. **Analyze Product Requirements**: Break down products into component tasks
    2. **Determine Worker Skills**: Assess worker capabilities and preferences
    3. **Calculate Optimal Assignment**: Match workers to tasks based on skills and preferences
    4. **Generate Schedule**: Create a time-slot based schedule for each worker
    5. **Optimize for Continuity**: Minimize task switching while ensuring flow
    
    ### Data Structure
    
    - **Products**: Defined by their component tasks and dependencies
    - **Workers**: Defined by their skills, preferences, and work patterns
    - **Tasks**: Defined by their skill requirements and duration
    
    ### Contact
    
    For support or feature requests, please contact the system administrator.
    """)

# Run the app with streamlit run app.py