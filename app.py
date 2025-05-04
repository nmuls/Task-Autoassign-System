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
    .highlight {
        background-color: #fff8e1;
        border-left: 5px solid #FFB300;
        padding: 5px;
    }
</style>
""", unsafe_allow_html=True)

# Helper functions
def calculate_skill_match(worker_skills, task_attributes):
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

def assign_tasks(products_to_produce, workers_df, products_df):
    """Groups identical tasks across all products and completes them before moving to next task type"""
    time_slots = generate_time_slots(8, 16)
    
    # Calculate total production days needed
    total_tasks = sum(
        len(products_df[products_df['Product'] == product]) * quantity 
        for product, quantity in products_to_produce.items())
    estimated_days = max(1, int(np.ceil(total_tasks / (len(workers_df) * len(time_slots) * 0.8))))
    
    # Create multi-day schedule
    schedule = {}
    for day in range(1, estimated_days + 1):
        schedule[day] = {worker: {slot: None for slot in time_slots} for worker in workers_df['Worker']}
    
    # Initialize tracking variables
    completed_task_ids = set()
    worker_stats = {
        worker: {
            'current_task': None,
            'current_product': None,
            'task_history': [],
            'completed_products': defaultdict(int),
            'total_tasks_completed': 0,
            'skill_utilization': 0,
            'time_spent_on_product': defaultdict(int)
        } for worker in workers_df['Worker']
    }
    
    # Create flattened list of all tasks across all products
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
    
    # Group tasks by their task name (not product)
    task_groups = defaultdict(list)
    for task in all_tasks:
        task_groups[task['task_name']].append(task)
    
    # Determine processing order based on task dependencies
    processing_order = []
    visited = set()
    
    def topological_sort(task_name):
        if task_name in visited:
            return
        visited.add(task_name)
        
        # Get requirements for this task type
        sample_task = next(t for t in all_tasks if t['task_name'] == task_name)
        if not pd.isna(sample_task['requirements']):
            for req in sample_task['requirements'].split(','):
                req = req.strip()
                # Find the task name that produces this requirement
                req_task_name = next(t['task_name'] for t in all_tasks if t['task_id'] == req)
                topological_sort(req_task_name)
        
        processing_order.append(task_name)
    
    # Build the processing order
    for task_name in task_groups:
        topological_sort(task_name)
    
    # Process each day
    for day in range(1, estimated_days + 1):
        # Process task groups in the determined order
        for task_name in processing_order:
            current_tasks = [t for t in task_groups[task_name] if not t['assigned']]
            if not current_tasks:
                continue
            
            # Check if requirements are met for this task group
            sample_task = current_tasks[0]
            if not pd.isna(sample_task['requirements']):
                reqs_met = all(
                    any(t['task_id'] == req.strip() and t['assigned'] 
                        for t in all_tasks)
                    for req in sample_task['requirements'].split(',')
                )
                if not reqs_met:
                    continue
            
            # Process each time slot in the day
            for slot_idx, time_slot in enumerate(time_slots):
                # Find available workers for this time slot
                available_workers = [worker for worker in workers_df['Worker'] 
                                   if schedule[day][worker][time_slot] is None]
                
                if not available_workers or not current_tasks:
                    continue
                
                # Assign tasks to available workers
                for worker_name in available_workers:
                    worker_data = workers_df[workers_df['Worker'] == worker_name].iloc[0]
                    
                    # Find best task for this worker
                    best_task = None
                    best_score = -1
                    
                    for task in current_tasks:
                        if task['assigned']:
                            continue
                            
                        # Calculate skill match (80% weight)
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
                        
                        # Prioritize continuing with same product (15% weight)
                        continuity_score = 0
                        if worker_stats[worker_name]['current_product'] == task['product']:
                            continuity_score = 0.15
                        
                        # Prioritize favorite products (5% weight)
                        product_pref = 0
                        if task['product'] == worker_data['FavoriteProduct1']:
                            product_pref = 0.05
                        elif task['product'] == worker_data['FavoriteProduct2']:
                            product_pref = 0.03
                        elif task['product'] == worker_data['FavoriteProduct3']:
                            product_pref = 0.02
                        
                        # Final score
                        final_score = skill_score * 0.8 + continuity_score + product_pref
                        
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
                                        'task_id': best_task['task_id']
                                    }
                            
                            # Update tracking
                            best_task['assigned'] = True
                            best_task['day_assigned'] = day
                            best_task['slot_assigned'] = slot_idx
                            completed_task_ids.add(best_task['task_id'])
                            worker_stats[worker_name]['task_history'].append(best_task)
                            worker_stats[worker_name]['completed_products'][best_task['product']] += 1
                            worker_stats[worker_name]['total_tasks_completed'] += 1
                            worker_stats[worker_name]['current_task'] = best_task['task_name']
                            worker_stats[worker_name]['current_product'] = best_task['product']
                            worker_stats[worker_name]['time_spent_on_product'][best_task['product']] += best_task['duration']
                            
                            # Update skill utilization
                            skill_match = calculate_skill_match(
                                worker_data,
                                {
                                    'Bending': best_task['bending'],
                                    'Gluing': best_task['gluing'],
                                    'Assembling': best_task['assembling'],
                                    'EdgeScrap': best_task['edge_scrap'],
                                    'OpenPaper': best_task['open_paper'],
                                    'QualityControl': best_task['quality_control']
                                }
                            )
                            worker_stats[worker_name]['skill_utilization'] = (
                                worker_stats[worker_name]['skill_utilization'] * 
                                (worker_stats[worker_name]['total_tasks_completed'] - 1) + 
                                skill_match
                            ) / worker_stats[worker_name]['total_tasks_completed']
                            
                            # Remove the assigned task from current tasks
                            current_tasks.remove(best_task)
    
    # Calculate completion statistics
    completion_stats = {
        'total_tasks': len(all_tasks),
        'completed_tasks': sum(1 for t in all_tasks if t['assigned']),
        'completion_percentage': (sum(1 for t in all_tasks if t['assigned']) / len(all_tasks) * 100) if all_tasks else 0,
        'tasks_by_day': {day: sum(1 for t in all_tasks if t['day_assigned'] == day) 
                        for day in range(1, estimated_days + 1)},
        'tasks_by_product': {product: sum(1 for t in all_tasks if t['product'] == product and t['assigned']) 
                            for product in products_to_produce.keys()},
        'worker_tasks': {worker: worker_stats[worker]['total_tasks_completed'] for worker in workers_df['Worker']},
        'estimated_days': estimated_days
    }
    
    return schedule, completion_stats, worker_stats

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
        
        1. Prioritizing tasks based on dependencies
        2. Matching workers to tasks based on skills
        3. Minimizing task switching for workers
        4. Balancing workload across available workers
        
        Use the navigation panel on the left to explore different sections of the application.
        """)
    
    with col2:
        st.image("https://cdn.pixabay.com/photo/2018/03/10/12/00/teamwork-3213924_1280.jpg", width=300)
    
    st.markdown("""
    ### How it works
    
    1. **Product Database**: View and manage products and their production tasks
    2. **Worker Database**: Manage worker profiles and their skill attributes
    3. **Production Order**: Create production orders and generate optimized schedules
    
    Get started by navigating to the **Production Order** page to create your first optimized schedule.
    """)

elif page == "Product Database":
    st.markdown('<div class="main-header">Product Database</div>', unsafe_allow_html=True)
    
    # Display product list
    st.markdown('<div class="sub-header">Products</div>', unsafe_allow_html=True)
    
    # Group products and show their tasks
    for product in unique_products:
        with st.expander(f"**{product}**"):
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
        with st.expander(f"**{worker['Worker']}**"):
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
                st.write("**Product Preferences:**")
                st.write(f"1. {worker['FavoriteProduct1']}")
                st.write(f"2. {worker['FavoriteProduct2']}")
                st.write(f"3. {worker['FavoriteProduct3']}")

elif page == "Production Order":
    st.markdown('<div class="main-header">Production Order</div>', unsafe_allow_html=True)
    
    st.markdown("""
    ### Create a production order to generate an optimized schedule
    
    Select products and quantities to generate an optimized work schedule.
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
        
        # Worker selection
        st.markdown('<div class="sub-header">Available Workers</div>', unsafe_allow_html=True)
        worker_availability = st.multiselect("Select available workers", 
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
            
            # Generate schedule
            schedule, completion_stats, worker_stats = assign_tasks(
                product_quantities, available_workers_df, products_df
            )
        
        # Display results
        st.success(f"Schedule generated! Task completion: {completion_stats['completion_percentage']:.1f}%")
        st.info(f"Estimated production days needed: {completion_stats['estimated_days']}")
        
        # Display task completion metrics
        st.markdown('<div class="sub-header">Task Completion</div>', unsafe_allow_html=True)
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Total Tasks", completion_stats['total_tasks'])
            
        with col2:
            st.metric("Completed Tasks", completion_stats['completed_tasks'])
            
        with col3:
            st.metric("Completion Rate", f"{completion_stats['completion_percentage']:.1f}%")
        
        # Task completion by product
        st.markdown("#### Tasks by Product")
        
        product_cols = st.columns(len(product_quantities))
        for i, (product, count) in enumerate(completion_stats['tasks_by_product'].items()):
            with product_cols[i % len(product_cols)]:
                total_product_tasks = sum(1 for task in products_df[products_df['Product'] == product]) * product_quantities[product]
                completion = (count / total_product_tasks) * 100 if total_product_tasks > 0 else 0
                st.metric(product, f"{count}/{total_product_tasks}", f"{completion:.1f}%")
        
        # Worker assignment visualization
        st.markdown('<div class="sub-header">Worker Assignments</div>', unsafe_allow_html=True)
        
        # Create tabs for each day
        day_tabs = st.tabs([f"Day {day}" for day in range(1, completion_stats['estimated_days'] + 1)])
        
        # Process each day
        time_slots = generate_time_slots(8, 16)
        
        for day_idx, day_tab in enumerate(day_tabs):
            day = day_idx + 1
            
            with day_tab:
                # Create a pivoted schedule table with workers as columns
                # First, create a dictionary to store task information
                worker_schedule = {}
                
                # Initialize with all time slots for each worker
                for worker in worker_availability:
                    worker_schedule[worker] = {slot: "" for slot in time_slots}
                
                # Fill in the tasks
                for worker, slots in schedule[day].items():
                    for slot, task in slots.items():
                        if task is not None:
                            # Create a formatted task string with product and task info
                            task_info = f"{task['product']} - {task['task']}"
                            worker_schedule[worker][slot] = task_info
                
                # Create a DataFrame with time slots as rows and workers as columns
                schedule_table = pd.DataFrame({
                    'Time': time_slots
                })
                
                # Add a column for each worker
                for worker in worker_availability:
                    schedule_table[worker] = schedule_table['Time'].map(worker_schedule[worker])
                
                # Set Time as index to make it the first column
                schedule_table = schedule_table.set_index('Time')
                
                # Display the table
                st.markdown(f"### Day {day} Schedule")
                st.dataframe(schedule_table, use_container_width=True)
        
        # Display detailed worker statistics
        st.markdown('<div class="sub-header">Worker Performance</div>', unsafe_allow_html=True)
        
        # Create worker performance metrics
        perf_data = []
        for worker, stats in worker_stats.items():
            if worker in worker_availability:
                perf_data.append({
                    'Worker': worker,
                    'Tasks Completed': stats['total_tasks_completed'],
                    'Products Worked': len(stats['completed_products']),
                    'Skill Utilization (%)': stats['skill_utilization'] * 100,
                    'Main Product': max(stats['time_spent_on_product'].items(), key=lambda x: x[1])[0] if stats['time_spent_on_product'] else "None"
                })
        
        if perf_data:
            perf_df = pd.DataFrame(perf_data)
            
            # Create a bar chart of tasks completed
            tasks_chart = alt.Chart(perf_df).mark_bar().encode(
                x=alt.X('Worker:N', sort='-y', title='Worker'),
                y=alt.Y('Tasks Completed:Q', title='Tasks Completed'),
                color=alt.Color('Skill Utilization (%):Q', scale=alt.Scale(scheme='greenblue')),
                tooltip=['Worker', 'Tasks Completed', 'Products Worked', 'Skill Utilization (%)', 'Main Product']
            ).properties(
                width=600,
                height=300,
                title="Worker Task Completion"
            )
            
            st.altair_chart(tasks_chart, use_container_width=True)
            
            # Also display the data as a table for clarity
            st.subheader("Worker Performance Details")
            st.dataframe(perf_df, use_container_width=True)
            
            # Create a download link for the schedule
            schedule_export = []
            for day in range(1, completion_stats['estimated_days'] + 1):
                for worker, slots in schedule[day].items():
                    for slot, task in slots.items():
                        if task is not None:
                            schedule_export.append({
                                'Day': day,
                                'Worker': worker,
                                'Time': slot,
                                'Product': task['product'],
                                'Task': task['task'],
                                'TaskID': task['task_id']
                            })
            
            if schedule_export:
                export_df = pd.DataFrame(schedule_export)
                st.markdown(get_table_download_link(export_df, 'schedule.csv', 'Download Schedule CSV'), unsafe_allow_html=True)

elif page == "About":
    st.markdown('<div class="main-header">About</div>', unsafe_allow_html=True)
    st.markdown("""
    ### Task Auto-Assignment System
    
    This application is designed to optimize production scheduling by:
    
    - Automatically assigning tasks to workers based on their skills
    - Prioritizing tasks with no dependencies first
    - Minimizing task switching for workers
    - Balancing workload across available workers
    
    The system calculates the estimated production days needed based on the total task volume and available workers.
    """)