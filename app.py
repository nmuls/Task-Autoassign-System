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

def check_requirements_met(completed_tasks, requirements):
    """Check if all requirement tasks are completed"""
    if not requirements or pd.isna(requirements):
        return True
        
    required_tasks = [req.strip() for req in str(requirements).split(',')]
    return all(req in completed_tasks for req in required_tasks)

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

def assign_tasks(products_to_produce, workers_df, products_df, days=None):
    """Main algorithm to assign tasks to workers based on fixed/flow roles"""
    # Auto-calculate days if not specified
    if days is None:
        days = calculate_required_days(products_to_produce, workers_df, products_df)
    
    time_slots = generate_time_slots(8, 16)
    
    # Create multi-day schedule
    schedule = {}
    for day in range(1, days + 1):
        schedule[day] = {worker: {slot: None for slot in time_slots} for worker in workers_df['Worker']}
    
    # Initialize tracking variables
    completed_tasks = set()
    task_completion_counts = defaultdict(int)  # Track how many of each task have been completed
    worker_stats = {
        worker: {
            'current_role': None,
            'fixed_task': None,  # The task a fixed worker is assigned to
            'fixed_tasks': set(),  # Set of task IDs this fixed worker focuses on
            'task_history': [],
            'completed_products': defaultdict(int),
            'total_tasks_completed': 0
        } for worker in workers_df['Worker']
    }
    
    # Determine worker roles based on FlowPreference
    worker_roles = {}
    for _, worker in workers_df.iterrows():
        worker_name = worker['Worker']
        flow_pref = worker['FlowPreference']
        # Higher preference value means worker prefers flow role
        worker_roles[worker_name] = 'flow' if flow_pref >= 0.6 else 'fixed'
    
    # Build dependency graph for all tasks in all products
    dependency_graph = {}
    task_products = {}  # Map task ID to product
    task_durations = {}  # Map task ID to duration
    task_requirements_count = {}  # Map task ID to number of required tasks
    task_details = {}  # Store complete task details
    
    for product, quantity in products_to_produce.items():
        product_tasks = products_df[products_df['Product'] == product]
        
        for _, task in product_tasks.iterrows():
            task_id = task['Result']
            task_products[task_id] = product
            task_durations[task_id] = task['DurationSlot']
            task_details[task_id] = {
                'product': product,
                'task_name': task['Task'],
                'bending': task['Bending'],
                'gluing': task['Gluing'],
                'assembling': task['Assembling'],
                'edge_scrap': task['EdgeScrap'],
                'open_paper': task['OpenPaper'],
                'quality_control': task['QualityControl'],
                'duration': task['DurationSlot'],
            }
            
            # Process requirements
            requirements = []
            if not pd.isna(task['Requirements']):
                requirements = [req.strip() for req in str(task['Requirements']).split(',')]
            
            dependency_graph[task_id] = requirements
            task_requirements_count[task_id] = len(requirements)
    
    # Flatten tasks from all products with quantities
    all_tasks = []
    for product, quantity in products_to_produce.items():
        product_tasks = products_df[products_df['Product'] == product].copy()
        for _, task in product_tasks.iterrows():
            for _ in range(quantity):
                all_tasks.append({
                    'product': product,
                    'task_name': task['Task'],
                    'task_id': task['Result'],
                    'requirements': task['Requirements'],
                    'duration': task['DurationSlot'],
                    'bending': task['Bending'],
                    'gluing': task['Gluing'],
                    'assembling': task['Assembling'],
                    'edge_scrap': task['EdgeScrap'],
                    'open_paper': task['OpenPaper'],
                    'quality_control': task['QualityControl'],
                    'assigned': False,
                    'completed': False,
                    'day_assigned': None,
                    'slot_assigned': None
                })
    
    # Group similar tasks by their attributes for fixed role assignment
    task_groups = {}
    for task in all_tasks:
        if task['assigned']:
            continue
            
        key = (task['bending'], task['gluing'], task['assembling'], 
               task['edge_scrap'], task['open_paper'], task['quality_control'])
        if key not in task_groups:
            task_groups[key] = []
        task_groups[key].append(task)
    
    # Identify starter tasks (tasks with no requirements) across all products
    starter_tasks = {}
    for task_id, reqs in dependency_graph.items():
        if not reqs:  # No requirements
            product = task_products[task_id]
            if product not in starter_tasks:
                starter_tasks[product] = []
            starter_tasks[product].append(task_id)
    
    # Initial assignment of fixed workers to starter tasks
    for worker_name, role in worker_roles.items():
        if role == 'fixed':
            worker_data = workers_df[workers_df['Worker'] == worker_name].iloc[0]
            
            # Find best starter task for this fixed worker
            best_task_id = None
            best_score = -1
            
            for product, task_ids in starter_tasks.items():
                for task_id in task_ids:
                    task_detail = task_details[task_id]
                    
                    # Calculate skill match
                    skill_score = calculate_skill_match(
                        worker_data,
                        {
                            'Bending': task_detail['bending'],
                            'Gluing': task_detail['gluing'],
                            'Assembling': task_detail['assembling'],
                            'EdgeScrap': task_detail['edge_scrap'],
                            'OpenPaper': task_detail['open_paper'],
                            'QualityControl': task_detail['quality_control']
                        }
                    )
                    
                    # Product preference
                    product_pref = 0
                    if product == worker_data['FavoriteProduct1']:
                        product_pref = 0.1
                    elif product == worker_data['FavoriteProduct2']:
                        product_pref = 0.05
                    
                    # Final score
                    final_score = skill_score + product_pref
                    
                    if final_score > best_score:
                        best_score = final_score
                        best_task_id = task_id
            
            if best_task_id:
                # Assign this task type to the worker
                worker_stats[worker_name]['fixed_tasks'].add(best_task_id)
    
    # Process each day
    for day in range(1, days + 1):
        # Process each time slot in the day
        for slot_idx, time_slot in enumerate(time_slots):
            # Find available workers for this time slot
            available_workers = [worker for worker in workers_df['Worker'] 
                                if schedule[day][worker][time_slot] is None]
            
            if not available_workers:
                continue
            
            # Update which tasks have their requirements met based on completed tasks
            eligible_tasks = []
            for task in all_tasks:
                if task['assigned']:
                    continue
                    
                # Check if requirements are met
                requirements_met = check_requirements_met(
                    completed_tasks, task['requirements']
                )
                
                if requirements_met:
                    eligible_tasks.append(task)
            
            if not eligible_tasks:
                continue
            
            # First, handle fixed workers
            for worker_name in [w for w in available_workers if worker_roles[w] == 'fixed']:
                worker_data = workers_df[workers_df['Worker'] == worker_name].iloc[0]
                fixed_tasks = worker_stats[worker_name]['fixed_tasks']
                
                # Find best task for this fixed worker
                best_task = None
                
                # First priority: continue with assigned fixed tasks
                if fixed_tasks:
                    for task in eligible_tasks:
                        if task['task_id'] in fixed_tasks:
                            best_task = task
                            break
                
                # If no assigned fixed task is eligible, find a new task to assign
                if not best_task and len(fixed_tasks) < 2:  # Limit fixed tasks per worker
                    # Prioritize starter tasks
                    starter_task_ids = [task_id for product_tasks in starter_tasks.values() 
                                      for task_id in product_tasks]
                    
                    for task in eligible_tasks:
                        if task['task_id'] in starter_task_ids:
                            best_task = task
                            worker_stats[worker_name]['fixed_tasks'].add(task['task_id'])
                            break
                
                # Assign the best task if found
                if best_task:
                    # Check if task fits in remaining slots
                    remaining_slots = len(time_slots) - slot_idx
                    if best_task['duration'] <= remaining_slots:
                        # Assign task for its duration
                        for i in range(int(best_task['duration'])):
                            if slot_idx + i < len(time_slots):
                                current_slot = time_slots[slot_idx + i]
                                schedule[day][worker_name][current_slot] = {
                                    'product': best_task['product'],
                                    'task': best_task['task_name'],
                                    'task_id': best_task['task_id'],
                                    'role': 'fixed'
                                }
                        
                        # Update tracking
                        best_task['assigned'] = True
                        best_task['day_assigned'] = day
                        best_task['slot_assigned'] = slot_idx
                        completed_tasks.add(best_task['task_id'])
                        task_completion_counts[best_task['task_id']] += 1
                        worker_stats[worker_name]['task_history'].append(best_task)
                        worker_stats[worker_name]['completed_products'][best_task['product']] += 1
                        worker_stats[worker_name]['total_tasks_completed'] += 1
                        
                        # Remove assigned task from eligible tasks
                        eligible_tasks.remove(best_task)
            
            # Then handle flow workers
            for worker_name in [w for w in available_workers if worker_roles[w] == 'flow' and schedule[day][w][time_slot] is None]:
                worker_data = workers_df[workers_df['Worker'] == worker_name].iloc[0]
                
                # Flow workers prioritize advancing the product flow
                best_task = None
                best_score = -1
                current_product = None
                
                # Check if worker is in the middle of a product flow
                if worker_stats[worker_name]['task_history']:
                    last_task = worker_stats[worker_name]['task_history'][-1]
                    current_product = last_task['product']
                
                for task in eligible_tasks:
                    # Prioritize continuing current product flow first
                    product_continuation = 0
                    if current_product and task['product'] == current_product:
                        product_continuation = 0.3
                    
                    # Calculate skill match
                    skill_score = calculate_skill_match(
                        worker_data, 
                        {
                            'Bending': task['bending'],
                            'Gluing': task['gluing'],
                            'Assembling': task['assembling'],
                            'EdgeScrap': task['edge_scrap'],
                            'OpenPaper': task['open_paper'],
                            'QualityControl': task['quality_control']
                        }
                    )
                    
                    # Prioritize advancing tasks (higher in dependency chain)
                    advancement_score = 0
                    if not pd.isna(task['requirements']) and task['requirements']:
                        advancement_score = 0.2
                    
                    # Product preference
                    product_pref = 0
                    if task['product'] == worker_data['FavoriteProduct1']:
                        product_pref = 0.1
                    elif task['product'] == worker_data['FavoriteProduct2']:
                        product_pref = 0.05
                    
                    # Final score with emphasis on flow and advancement
                    final_score = skill_score * 0.4 + product_continuation + advancement_score + product_pref
                    
                    if final_score > best_score:
                        best_score = final_score
                        best_task = task
                
                # Assign the best task if found
                if best_task:
                    # Check if task fits in remaining slots
                    remaining_slots = len(time_slots) - slot_idx
                    if best_task['duration'] <= remaining_slots:
                        # Assign task for its duration
                        for i in range(int(best_task['duration'])):
                            if slot_idx + i < len(time_slots):
                                current_slot = time_slots[slot_idx + i]
                                schedule[day][worker_name][current_slot] = {
                                    'product': best_task['product'],
                                    'task': best_task['task_name'],
                                    'task_id': best_task['task_id'],
                                    'role': 'flow'
                                }
                        
                        # Update tracking
                        best_task['assigned'] = True
                        best_task['day_assigned'] = day
                        best_task['slot_assigned'] = slot_idx
                        completed_tasks.add(best_task['task_id'])
                        task_completion_counts[best_task['task_id']] += 1
                        worker_stats[worker_name]['task_history'].append(best_task)
                        worker_stats[worker_name]['completed_products'][best_task['product']] += 1
                        worker_stats[worker_name]['total_tasks_completed'] += 1
                        
                        # Remove assigned task from eligible tasks
                        eligible_tasks.remove(best_task)
    
    # Calculate task completion statistics
    completion_stats = {
        'total_tasks': len(all_tasks),
        'completed_tasks': sum(1 for task in all_tasks if task['assigned']),
        'completion_percentage': sum(1 for task in all_tasks if task['assigned']) / len(all_tasks) * 100 if all_tasks else 0,
        'tasks_by_day': {day: sum(1 for task in all_tasks if task['day_assigned'] == day) for day in range(1, days + 1)},
        'tasks_by_product': {product: sum(1 for task in all_tasks if task['product'] == product and task['assigned']) 
                            for product in products_to_produce.keys()},
        'worker_tasks': {worker: worker_stats[worker]['total_tasks_completed'] for worker in workers_df['Worker']}
    }
    
    return schedule, completion_stats, worker_stats, worker_roles, days

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
            # Simulate processing time (could be removed in production)
            progress_bar = st.progress(0)
            for i in range(100):
                time.sleep(0.01)
                progress_bar.progress(i + 1)
            
            # Generate schedule with auto-calculated days
            schedule, completion_stats, worker_stats, worker_roles, days = assign_tasks(
                product_quantities, available_workers_df, products_df, None
            )
        
        # Display results
        st.success(f"Schedule generated for {days} days! Task completion: {completion_stats['completion_percentage']:.1f}%")
        
        # Display task completion metrics
        st.markdown('<div class="sub-header">Task Completion</div>', unsafe_allow_html=True)
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Total Tasks", completion_stats['total_tasks'])
        
        with col2:
            st.metric("Completed Tasks", completion_stats['completed_tasks'])
        
        with col3:
            st.metric("Completion Rate", f"{completion_stats['completion_percentage']:.1f}%")
        
        # Display product completion
        st.markdown('<div class="sub-header">Product Completion</div>', unsafe_allow_html=True)
        
        product_completion = pd.DataFrame({
            'Product': list(completion_stats['tasks_by_product'].keys()),
            'Tasks Completed': list(completion_stats['tasks_by_product'].values())
        })
        
        st.dataframe(product_completion)
        
        # Display worker performance as a table instead of bar graphs
        st.markdown('<div class="sub-header">Worker Performance</div>', unsafe_allow_html=True)
        
        # Create worker performance dataframe
        worker_performance = []
        for worker_name in worker_availability:
            # Calculate products completed
            products_completed = dict(worker_stats[worker_name]['completed_products'])
            product_str = ", ".join([f"{p}: {c}" for p, c in products_completed.items() if c > 0])
            
            # Get worker role
            role = worker_roles.get(worker_name, "flow")  # Default to flow if not found
            
            worker_performance.append({
                'Worker': worker_name,
                'Role': role.capitalize(),
                'Tasks Completed': worker_stats[worker_name]['total_tasks_completed'],
                'Products Completed': product_str
            })
        
        performance_df = pd.DataFrame(worker_performance)
        st.dataframe(performance_df)
        
        # Display daily schedule
        st.markdown('<div class="sub-header">Daily Schedule</div>', unsafe_allow_html=True)
        
        # Create tabs for each day
        day_tabs = st.tabs([f"Day {day}" for day in range(1, days + 1)])
        
        for day_idx, day_tab in enumerate(day_tabs):
            day = day_idx + 1
            with day_tab:
                # Convert schedule to DataFrame for easier display
                day_schedule_data = []
                
                for worker in worker_availability:
                    for time_slot in generate_time_slots(8, 16):
                        task_info = schedule[day][worker][time_slot]
                        if task_info:
                            day_schedule_data.append({
                                'Worker': worker,
                                'Time': time_slot,
                                'Product': task_info['product'],
                                'Task': task_info['task'],
                                'TaskID': task_info['task_id'],
                                'Role': task_info['role']
                            })
                
                if day_schedule_data:
                    day_df = pd.DataFrame(day_schedule_data)
                    
                    # Create a pivot table with Time as rows and Worker as columns
                    pivot_df = day_df.pivot(index='Time', columns='Worker', values='Task')
                    
                    # Apply styling
                    def color_cells(val):
                        if pd.isna(val):
                            return ''
                        
                        role_info = day_df[(day_df['Worker'] == pivot_df.columns.name) & 
                                          (day_df['Time'] == pivot_df.index.name) & 
                                          (day_df['Task'] == val)]
                        
                        if not role_info.empty:
                            role = role_info.iloc[0]['Role']
                            product = role_info.iloc[0]['Product']
                            
                            # Different colors for fixed vs flow roles
                            if role == 'fixed':
                                return f'background-color: #e3f2fd; border-left: 3px solid #1976D2;'
                            else:
                                return f'background-color: #e8f5e9; border-left: 3px solid #43A047;'
                        return ''
                    
                    # Format the pivot table to show task details on hover
                    def format_tasks(val):
                        if pd.isna(val):
                            return ''
                        
                        task_info = day_df[(day_df['Worker'] == pivot_df.columns.name) & 
                                          (day_df['Time'] == pivot_df.index.name) & 
                                          (day_df['Task'] == val)]
                        
                        if not task_info.empty:
                            product = task_info.iloc[0]['Product']
                            return f"{product}: {val}"
                        return val
                    
                    # Display pivoted schedule
                    styled_pivot = pivot_df.style.applymap(color_cells)
                    
                    # Add tooltip with task details
                    task_details = {}
                    for _, row in day_df.iterrows():
                        task_details[(row['Time'], row['Worker'])] = f"{row['Product']}: {row['Task']}"
                    
                    st.dataframe(styled_pivot, height=600)
                    
                    # Create downloadable CSV
                    st.markdown(get_table_download_link(day_df, f"day_{day}_schedule.csv", f"Download Day {day} Schedule"), unsafe_allow_html=True)
                else:
                    st.info(f"No tasks scheduled for Day {day}")
        
        # Create overall schedule download
        all_schedule_data = []
        for day in range(1, days + 1):
            for worker in worker_availability:
                for time_slot in generate_time_slots(8, 16):
                    task_info = schedule[day][worker][time_slot]
                    if task_info:
                        all_schedule_data.append({
                            'Day': day,
                            'Worker': worker,
                            'Time': time_slot,
                            'Product': task_info['product'],
                            'Task': task_info['task'],
                            'TaskID': task_info['task_id'],
                            'Role': task_info['role']
                        })
        
        if all_schedule_data:
            all_schedule_df = pd.DataFrame(all_schedule_data)
            st.markdown(get_table_download_link(all_schedule_df, "complete_schedule.csv", "Download Complete Schedule"), unsafe_allow_html=True)

elif page == "About":
    st.markdown('<div class="main-header">About the System</div>', unsafe_allow_html=True)
    
    st.markdown("""
    ### Task Auto-Assignment System
    
    This system helps production managers optimize their workforce allocation by:
    
    1. *Auto-calculating* production days needed based on order volume
    2. *Optimizing* worker assignments based on their skills and preferences
    3. *Balancing* fixed and flow roles for maximum efficiency
    4. *Respecting* task dependencies and requirements
    
    #### Key Features
    
    - *Fixed vs Flow Roles*: Workers can be assigned to fixed roles (repeating similar tasks) or flow roles (following product flow)
    - *Skill Matching*: Tasks are assigned based on worker skills and preferences
    - *Product Continuity*: The system tries to keep workers on the same product when beneficial
    - *Task Grouping*: Similar tasks are grouped together for efficiency
    
    #### How to Use
    
    1. Start by creating a production order on the Production Order page
    2. Select products and quantities
    3. Customize worker availability if needed
    4. Generate an optimized schedule
    5. View and download the schedule
    """)
    
    st.image("https://cdn.pixabay.com/photo/2018/01/18/21/50/scheduling-3091268_1280.png", width=500)