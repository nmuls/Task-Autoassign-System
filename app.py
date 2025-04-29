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

def assign_tasks(products_to_produce, workers_df, products_df, days=1):
    """Main algorithm to assign tasks to workers based on skills and task similarity"""
    time_slots = generate_time_slots(8, 16)
    
    # Create multi-day schedule
    schedule = {}
    for day in range(1, days + 1):
        schedule[day] = {worker: {slot: None for slot in time_slots} for worker in workers_df['Worker']}
    
    # Initialize tracking variables
    completed_tasks = set()
    worker_stats = {
        worker: {
            'current_role': None,
            'fixed_task': None,  # The task a fixed worker is currently focused on
            'fixed_task_count': 0,
            'task_history': [],
            'completed_products': defaultdict(int),
            'total_tasks_completed': 0
        } for worker in workers_df['Worker']
    }
    
    # Initialize worker roles dictionary
    worker_roles = {}
    
    # Flatten tasks from all products
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
    
    # Sort tasks by requirements (tasks with no requirements first)
    all_tasks.sort(key=lambda x: 0 if not x['requirements'] or pd.isna(x['requirements']) else 1)
    
    # Group similar tasks by their attributes
    task_groups = {}
    for task in all_tasks:
        key = (task['bending'], task['gluing'], task['assembling'], 
               task['edge_scrap'], task['open_paper'], task['quality_control'])
        if key not in task_groups:
            task_groups[key] = []
        task_groups[key].append(task)
    
    # Find the most common task attribute group to prioritize fixed workers
    group_counts = {k: len(v) for k, v in task_groups.items()}
    if group_counts:
        most_common_group = max(group_counts, key=group_counts.get)
        most_common_tasks = task_groups[most_common_group]
    else:
        most_common_tasks = []
    
    # Assign worker roles based on preference and most common tasks
    for _, worker in workers_df.iterrows():
        flow_pref = worker['FlowPreference']
        worker_name = worker['Worker']
        
        # Determine if worker should be fixed or flow based on their preference
        if flow_pref > 0.6 and most_common_tasks:
            worker_roles[worker_name] = 'fixed'
        else:
            worker_roles[worker_name] = 'flow'
    
    # Calculate how many fixed workers we need based on the task distribution
    num_fixed_workers_needed = min(len(most_common_tasks) // 2 + 1, len(worker_roles))
    
    # Ensure we have enough fixed workers for the most common tasks
    fixed_workers_count = sum(1 for role in worker_roles.values() if role == 'fixed')
    
    if fixed_workers_count < num_fixed_workers_needed:
        # Convert some flow workers to fixed by preference
        flow_workers = [w for w, r in worker_roles.items() if r == 'flow']
        flow_workers.sort(key=lambda w: workers_df[workers_df['Worker'] == w]['FlowPreference'].iloc[0], reverse=True)
        
        for worker in flow_workers[:num_fixed_workers_needed - fixed_workers_count]:
            worker_roles[worker] = 'fixed'
    
    # Process each day
    for day in range(1, days + 1):
        # Process each time slot in the day
        for slot_idx, time_slot in enumerate(time_slots):
            # Find available workers for this time slot
            available_workers = [worker for worker in workers_df['Worker'] if schedule[day][worker][time_slot] is None]
            
            if not available_workers:
                continue
                
            # Find tasks whose requirements are met
            eligible_tasks = [task for task in all_tasks 
                             if not task['assigned'] and check_requirements_met(completed_tasks, task['requirements'])]
            
            if not eligible_tasks:
                continue
            
            # Group eligible tasks by their attribute similarities
            eligible_groups = {}
            for task in eligible_tasks:
                key = (task['bending'], task['gluing'], task['assembling'], 
                       task['edge_scrap'], task['open_paper'], task['quality_control'])
                if key not in eligible_groups:
                    eligible_groups[key] = []
                eligible_groups[key].append(task)
            
            # First, assign fixed workers to their preferred task groups
            for worker_name in [w for w in available_workers if worker_roles[w] == 'fixed']:
                worker_data = workers_df[workers_df['Worker'] == worker_name].iloc[0]
                
                # If worker already has a fixed task, continue with it if possible
                if worker_stats[worker_name]['fixed_task'] is not None:
                    fixed_task_key = (
                        worker_stats[worker_name]['fixed_task']['bending'],
                        worker_stats[worker_name]['fixed_task']['gluing'],
                        worker_stats[worker_name]['fixed_task']['assembling'],
                        worker_stats[worker_name]['fixed_task']['edge_scrap'],
                        worker_stats[worker_name]['fixed_task']['open_paper'],
                        worker_stats[worker_name]['fixed_task']['quality_control']
                    )
                    
                    # Check if there are eligible tasks of the same type
                    if fixed_task_key in eligible_groups and eligible_groups[fixed_task_key]:
                        best_task = eligible_groups[fixed_task_key][0]
                        
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
                            
                            # Update worker stats
                            best_task['assigned'] = True
                            best_task['day_assigned'] = day
                            best_task['slot_assigned'] = slot_idx
                            completed_tasks.add(best_task['task_id'])
                            worker_stats[worker_name]['task_history'].append(best_task)
                            worker_stats[worker_name]['completed_products'][best_task['product']] += 1
                            worker_stats[worker_name]['total_tasks_completed'] += 1
                            worker_stats[worker_name]['fixed_task_count'] += 1
                            
                            # Remove the assigned task from eligible tasks
                            eligible_tasks.remove(best_task)
                            eligible_groups[fixed_task_key].remove(best_task)
                            continue
                
                # If no fixed task or no eligible tasks of the same type, find a new task
                best_task = None
                best_score = -1
                
                # Prioritize tasks from most common group for fixed workers
                for group_key, group_tasks in eligible_groups.items():
                    if not group_tasks:
                        continue
                    
                    # Calculate group score based on number of tasks and skill match
                    group_size_score = len(group_tasks) / len(eligible_tasks)
                    
                    # Calculate skill match for this group
                    skill_score = calculate_skill_match(
                        worker_data,
                        {
                            'Bending': group_tasks[0]['bending'],
                            'Gluing': group_tasks[0]['gluing'],
                            'Assembling': group_tasks[0]['assembling'],
                            'EdgeScrap': group_tasks[0]['edge_scrap'],
                            'OpenPaper': group_tasks[0]['open_paper'],
                            'QualityControl': group_tasks[0]['quality_control']
                        }
                    )
                    
                    # Calculate product preference
                    product_pref = 0
                    if group_tasks[0]['product'] == worker_data['FavoriteProduct1']:
                        product_pref = 0.1
                    elif group_tasks[0]['product'] == worker_data['FavoriteProduct2']:
                        product_pref = 0.05
                    
                    # Calculate final score with emphasis on group size for fixed workers
                    final_score = skill_score * 0.4 + group_size_score * 0.5 + product_pref
                    
                    if final_score > best_score:
                        best_score = final_score
                        best_task = group_tasks[0]
                
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
                        
                        # Update worker stats
                        best_task['assigned'] = True
                        best_task['day_assigned'] = day
                        best_task['slot_assigned'] = slot_idx
                        completed_tasks.add(best_task['task_id'])
                        worker_stats[worker_name]['task_history'].append(best_task)
                        worker_stats[worker_name]['completed_products'][best_task['product']] += 1
                        worker_stats[worker_name]['total_tasks_completed'] += 1
                        worker_stats[worker_name]['fixed_task'] = best_task
                        worker_stats[worker_name]['fixed_task_count'] = 1
                        
                        # Remove the assigned task from eligible tasks
                        task_key = (
                            best_task['bending'],
                            best_task['gluing'],
                            best_task['assembling'],
                            best_task['edge_scrap'],
                            best_task['open_paper'],
                            best_task['quality_control']
                        )
                        eligible_tasks.remove(best_task)
                        eligible_groups[task_key].remove(best_task)
            
            # Then assign flow workers to tasks that need completion
            for worker_name in [w for w in available_workers if worker_roles[w] == 'flow' and schedule[day][w][time_slot] is None]:
                worker_data = workers_df[workers_df['Worker'] == worker_name].iloc[0]
                
                # Find best task based on skill match and product flow
                best_task = None
                best_score = -1
                
                for task in eligible_tasks:
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
                    
                    # Prioritize tasks that continue the product flow
                    flow_score = 0
                    if worker_stats[worker_name]['task_history']:
                        last_task = worker_stats[worker_name]['task_history'][-1]
                        if last_task['product'] == task['product']:
                            flow_score = 0.3
                    
                    # Prioritize favorite products
                    product_pref = 0
                    if task['product'] == worker_data['FavoriteProduct1']:
                        product_pref = 0.1
                    elif task['product'] == worker_data['FavoriteProduct2']:
                        product_pref = 0.05
                    
                    # Final score with emphasis on skill and flow
                    final_score = skill_score * 0.6 + flow_score + product_pref
                    
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
                        
                        # Update worker stats
                        best_task['assigned'] = True
                        best_task['day_assigned'] = day
                        best_task['slot_assigned'] = slot_idx
                        completed_tasks.add(best_task['task_id'])
                        worker_stats[worker_name]['task_history'].append(best_task)
                        worker_stats[worker_name]['completed_products'][best_task['product']] += 1
                        worker_stats[worker_name]['total_tasks_completed'] += 1
                        
                        # Remove the assigned task from eligible tasks
                        eligible_tasks.remove(best_task)
                        
                        # Remove from eligible groups as well
                        task_key = (
                            best_task['bending'],
                            best_task['gluing'],
                            best_task['assembling'],
                            best_task['edge_scrap'],
                            best_task['open_paper'],
                            best_task['quality_control']
                        )
                        if task_key in eligible_groups and best_task in eligible_groups[task_key]:
                            eligible_groups[task_key].remove(best_task)
    
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
                st.write("**Flow/Fixed Preference:**")
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
                
                st.write("**Product Preferences:**")
                st.write(f"1. {worker['FavoriteProduct1']}")
                st.write(f"2. {worker['FavoriteProduct2']}")
                st.write(f"3. {worker['FavoriteProduct3']}")

elif page == "Production Order":
    st.markdown('<div class="main-header">Production Order</div>', unsafe_allow_html=True)
    
    st.markdown("""
    ### Create a production order to generate an optimized schedule
    
    Select products and quantities, then customize parameters to generate an optimized work schedule.
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
            days = st.slider("Production Days", min_value=1, max_value=5, value=1)
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
            
            # Generate schedule
            schedule, completion_stats, worker_stats = assign_tasks(
                product_quantities, available_workers_df, products_df, days
            )
        
        # Display results
        st.success(f"Schedule generated! Task completion: {completion_stats['completion_percentage']:.1f}%")
        
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
        day_tabs = st.tabs([f"Day {day}" for day in range(1, days + 1)])
        
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
                
                # Add a color legend for worker roles
                role_legend = ""
                for worker in worker_availability:
                    role = worker_roles[worker] if 'worker_roles' in locals() else "Unknown"
                    role_color = "#1976D2" if role == "fixed" else "#43A047"
                    role_legend += f'<span style="color:{role_color}">■</span> {worker}: {role.capitalize()} &nbsp;&nbsp;'
                
                st.markdown(f"<div style='font-size:0.8em'>{role_legend}</div>", unsafe_allow_html=True)
                    
                    # Create worker role indicators
                st.markdown("#### Worker Roles")
                role_cols = st.columns(len(worker_availability))
                    
                for i, worker in enumerate(worker_availability):
                        with role_cols[i % len(role_cols)]:
                            role = worker_roles[worker] if 'worker_roles' in locals() else "Unknown"
                            role_class = "fixed-role" if role == "fixed" else "flow-role"
                            st.markdown(f"""
                            <div class="{role_class}">
                                <b>{worker}</b>: {role.capitalize()} Worker
                            </div>
                            """, unsafe_allow_html=True)
                else:
                    st.info(f"No tasks scheduled for Day {day}")
        
        # Display detailed worker statistics
        st.markdown('<div class="sub-header">Worker Performance</div>', unsafe_allow_html=True)
        
        # Create worker performance metrics
        perf_data = []
        for worker, stats in worker_stats.items():
            if worker in worker_availability:
                # Make sure we have some data to display
                tasks_completed = stats['total_tasks_completed'] if 'total_tasks_completed' in stats else 0
                role = worker_roles[worker] if 'worker_roles' in locals() else "Unknown"
                perf_data.append({
                    'Worker': worker,
                    'Tasks Completed': tasks_completed,
                    'Products Worked': len(stats['completed_products']) if 'completed_products' in stats else 0,
                    'Role': role
                })
        
        if perf_data:
            perf_df = pd.DataFrame(perf_data)
            
            # Ensure there's actual data to display
            if not perf_df.empty and perf_df['Tasks Completed'].sum() > 0:
                # Create a simple bar chart with Altair
                perf_chart = alt.Chart(perf_df).mark_bar().encode(
                    x=alt.X('Worker:N', sort='-y', title='Worker'),
                    y=alt.Y('Tasks Completed:Q', title='Tasks Completed'),
                    color=alt.Color('Role:N', scale=alt.Scale(domain=['fixed', 'flow'], 
                                                             range=['#1976D2', '#43A047'])),
                    tooltip=['Worker', 'Tasks Completed', 'Products Worked', 'Role']
                ).properties(
                    width=600,
                    height=300,
                    title="Worker Task Completion"
                )
                
                st.altair_chart(perf_chart, use_container_width=True)
            else:
                # As a backup, display a simple table
                st.warning("Not enough task completion data to generate chart. Displaying data table instead.")
                st.dataframe(perf_df, use_container_width=True)
            
            # Also display the data as a table for clarity
            st.subheader("Worker Performance Details")
            st.dataframe(perf_df, use_container_width=True)
        else:
            st.warning("No worker performance data available.")
            
            # Create a download link for the schedule
            schedule_export = []
            for day in range(1, days + 1):
                for worker, slots in schedule[day].items():
                    for slot, task in slots.items():
                        if task is not None:
                            schedule_export.append({
                                'Day': day,
                                'Worker': worker,
                                'Time': slot,
                                'Product': task['product'],
                                'Task': task['task'],
                                'TaskID': task['task_id'],
                                'Role': task['role']
                            })
            
            if schedule_export:
                export_df = pd.DataFrame(schedule_export)
                st.markdown(get_table_download_link(export_df, 'schedule.csv', 'Download Schedule CSV'), unsafe_allow_html=True)

elif page == "About":
    st.markdown('<div class="main-header">About this Application</div>', unsafe_allow_html=True)
    
    st.markdown("""
    ### Task Auto-Assignment System
    
    This application helps manufacturing facilities optimize their production scheduling by automatically assigning tasks to workers based on skills, preferences, and task requirements.
    
    #### Key Features:
    
    1. **Smart Worker Allocation**: Automatically assigns workers to tasks based on skill matching and preferences
    2. **Dual Work Mode**: Supports both "fixed" workers (who repeat similar tasks) and "flow" workers (who follow product progression)
    3. **Task Dependencies**: Respects the required order of operations for each product
    4. **Schedule Visualization**: Clear timeline view of worker assignments
    5. **Performance Metrics**: Track completion rates and worker productivity
    
    #### How the Algorithm Works:
    
    1. Tasks are grouped by their skill requirements to identify commonalities
    2. Workers are assigned "fixed" or "flow" roles based on task distribution and preferences
    3. Fixed workers are assigned to groups of similar tasks to maximize efficiency through repetition
    4. Flow workers follow product progression, focusing on completing products in sequence
    5. All task dependencies are respected to ensure quality production
    
    #### Using the Application:
    
    1. Navigate to the **Production Order** page
    2. Select products and quantities for production
    3. Set schedule parameters like production days and worker availability
    4. Generate and analyze the optimized schedule
    5. Export the schedule for implementation
    """,unsafe_allow_html=True)
    
