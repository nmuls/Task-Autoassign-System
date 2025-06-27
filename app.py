import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
from collections import defaultdict
import time
import io
import base64
import math

# Set page configuration
st.set_page_config(
    page_title="Task Auto-Assignment System",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS to fix layout issues
st.markdown("""
<style>
    .main .block-container {
        padding-left: 2rem;
        padding-right: 2rem;
        max-width: none;
    }
    
    .sidebar .sidebar-content {
        width: 21rem;
    }
    
    /* Ensure main content doesn't get cut off */
    .main {
        margin-left: 0;
    }
    
    /* Fix for wide layout */
    .stApp > div:first-child {
        margin-left: 0;
    }
    
    /* Specific fix for schedule tables */
    .stDataFrame, .stTable {
        width: 100% !important;
        overflow-x: auto !important;
    }
    
    /* Fix for tabs container */
    .stTabs [data-baseweb="tab-list"] {
        width: 100% !important;
    }
    
    /* Ensure schedule content is not cut off */
    .element-container {
        width: 100% !important;
    }
    
    /* Fix for dataframe display */
    div[data-testid="stDataFrame"] {
        width: 100% !important;
        overflow-x: auto !important;
    }
    
    /* Responsive adjustments */
    @media (max-width: 768px) {
        .main .block-container {
            padding-left: 1rem;
            padding-right: 1rem;
        }
    }
    
    /* Force full width for schedule content */
    .stDataFrame > div {
        width: 100% !important;
        max-width: none !important;
    }
</style>
""", unsafe_allow_html=True)

# --- Data Models for Simulation ---
class TaskSimulationData:
    def __init__(self, product_row):
        self.product = product_row["Product"]
        self.description = product_row["Task"]
        self.task_id = product_row["Result"]
        # Handle NaN requirements gracefully
        requirements_str = str(product_row["Requirements"])
        if pd.isna(product_row["Requirements"]) or requirements_str.lower() == "nan":
            self.requirements = []
        else:
            self.requirements = [req.strip() for req in requirements_str.split(",") if req.strip()]
        
        self.skill_requirements = {
            "Bending": product_row["Bending"] / 100, 
            "Gluing": product_row["Gluing"] / 100,
            "Assembling": product_row["Assembling"] / 100,
            "EdgeScrap": product_row["EdgeScrap"] / 100,
            "OpenPaper": product_row["OpenPaper"] / 100,
            "QualityControl": product_row["QualityControl"] / 100,
        }
        self.duration_slot = product_row["DurationSlot"]

    def __repr__(self):
        return f"TaskSimData(ID={self.task_id}, Product={self.product}, Req={self.requirements})"

class WorkerSimulationData:
    def __init__(self, worker_row):
        self.name = worker_row["Worker"]
        self.skills = {
            "Bending": worker_row["Bending"],
            "Gluing": worker_row["Gluing"],
            "Assembling": worker_row["Assembling"],
            "EdgeScrap": worker_row["EdgeScrap"],
            "OpenPaper": worker_row["OpenPaper"],
            "QualityControl": worker_row["QualityControl"],
        }
        self.favorite_products = [worker_row["FavoriteProduct1"], worker_row["FavoriteProduct2"], worker_row["FavoriteProduct3"]]
        
        # Simulation state
        self.is_available = True
        self.current_task_instance = None
        self.time_remaining_on_task = 0
        self.expected_completion_time = 0
        self.task_history = []
        self.is_aggressive = False
        self.aggressiveness_factor = np.random.uniform(0.2, 0.8)
        self.progression_score = 0
        self.completed_products_count = defaultdict(int)
        self.total_tasks_completed_units = 0
        self.skill_utilization_score = 0
        self.time_spent_on_product = defaultdict(int)
        self.current_product_focus = None
        
    def __repr__(self):
        return f"WorkerSimData(Name={self.name}, Available={self.is_available})"

class TaskInstance:
    def __init__(self, task_sim_data, instance_idx):
        self.task_sim_data = task_sim_data
        self.instance_id = f"{task_sim_data.task_id}_U{instance_idx}"
        self.product = task_sim_data.product
        self.task_id = task_sim_data.task_id
        self.description = task_sim_data.description
        self.requirements = task_sim_data.requirements
        self.skill_requirements = task_sim_data.skill_requirements
        self.duration_slot = task_sim_data.duration_slot
        
        self.status = "pending"
        self.progress_percentage = 0.0
        self.assigned_worker_name = None
        self.start_time_minutes = None
        self.completion_time_minutes = None
        self.assigned_history = []
        
    def __repr__(self):
        return f"TaskInstance(ID={self.instance_id}, TaskType={self.task_id}, Status={self.status}, Progress={self.progress_percentage:.1f}%)"

# --- Data Loading ---
@st.cache_data
def load_data():
    """Load data from CSV files in the same directory"""
    try:
        workers_df = pd.read_csv("workers.csv")
        products_df = pd.read_csv("products.csv")
        return workers_df, products_df
    except FileNotFoundError as e:
        st.error(f"File not found: {e}")
        st.error("Make sure 'workers.csv' dan 'products.csv' is in the same directory as this application.")
        st.stop()

# Helper functions
def calculate_skill_match(worker_skills, task_skill_requirements):
    """Calculate skill match score between worker and task"""
    total_score = 0
    num_relevant_skills = 0
    
    for skill_type, required_ratio in task_skill_requirements.items():
        if required_ratio > 0:
            worker_skill = worker_skills.get(skill_type, 0)
            score = worker_skill / max(0.01, required_ratio)
            total_score += score
            num_relevant_skills += 1
            
    return total_score / num_relevant_skills if num_relevant_skills > 0 else 0.1

def format_time(minutes):
    """Convert simulation minutes to HH:MM format"""
    hours_from_start = minutes // 60
    mins_past_hour = minutes % 60
    display_hour = 8 + hours_from_start
    return f"{int(display_hour):02d}:{int(mins_past_hour):02d}"

def get_task_group(task_id):
    """Returns a generic task group ID (e.g., 'ST1' and 'SL1' both map to 'T1')"""
    if task_id.startswith("ST"):
        return f"T{task_id[2:]}"
    elif task_id.startswith("SL"):
        return f"T{task_id[2:]}"
    elif task_id.startswith("BH"):
        return f"T{task_id[2:]}"
    return task_id # Fallback for other task IDs

def check_requirements_met(task_instance, inventory, partial_completions):
    """Check if task requirements are met, considering interchangeable requirements"""
    # ST1, SL1, BH1 tasks have no requirements - they can always start
    if not task_instance.requirements:
        return True
    
    for req_task_id in task_instance.requirements:
        # Check if any task from the same group as req_task_id has completed units or significant progress
        req_task_group = get_task_group(req_task_id)
        
        met_by_group = False
        for inv_task_id, completed_units in inventory.items():
            if get_task_group(inv_task_id) == req_task_group and completed_units >= 1:
                met_by_group = True
                break
        
        if not met_by_group:
            for pc in partial_completions:
                if get_task_group(pc["task_id"]) == req_task_group and pc["progress_percentage"] >= 50.0:
                    met_by_group = True
                    break
        
        if not met_by_group:
            return False
    return True

def get_earliest_available_tasks(all_task_instances, inventory, partial_completions):
    """Get earliest tasks that can be started (prioritizing tasks with no requirements)"""
    earliest_tasks = []
    for task_instance in all_task_instances:
        if task_instance.status == "pending" and not task_instance.requirements:
            earliest_tasks.append(task_instance)
    return earliest_tasks

def get_available_tasks(all_task_instances, inventory, partial_completions):
    """Get all tasks that can be started based on requirements"""
    available_tasks = []
    for task_instance in all_task_instances:
        if task_instance.status == "pending" and check_requirements_met(task_instance, inventory, partial_completions):
            available_tasks.append(task_instance)
    return available_tasks

def prioritize_tasks_for_flow(all_available_tasks, earliest_tasks, all_task_instances, inventory, partial_completions):
    """Prioritize tasks to optimize production flow and worker transitions"""
    prioritized_tasks = []
    
    # 1. Prioritize tasks that are earliest (no requirements)
    prioritized_tasks.extend(sorted(earliest_tasks, key=lambda t: t.task_id))
    
    # 2. Add other available tasks that can enable progression
    other_tasks = [t for t in all_available_tasks if t not in earliest_tasks]
    prioritized_tasks.extend(sorted(other_tasks, key=lambda t: (len(t.requirements), t.task_id)))
    
    return prioritized_tasks

def assign_worker_to_task(worker, task, current_time_minutes, slot_duration_minutes):
    """Assign a worker to a task"""
    worker.is_available = False
    worker.current_task_instance = task
    worker.time_remaining_on_task = task.duration_slot * slot_duration_minutes
    
    task.status = "in_progress"
    task.assigned_worker_name = worker.name
    task.start_time_minutes = current_time_minutes

# --- Core Scheduling Logic ---
def assign_tasks(products_to_produce, available_workers_df, products_df, slot_duration_minutes=30):
    """Enhanced task assignment with dynamic worker transitions and interchangeable requirements"""
    try:
        # Initialize simulation data structures
        task_sim_data_map = {row["Result"]: TaskSimulationData(row) for _, row in products_df.iterrows()}
        worker_sim_data_map = {row["Worker"]: WorkerSimulationData(row) for _, row in available_workers_df.iterrows()}
        
        # Generate unique TaskInstance objects
        all_task_instances = []
        instance_counter = defaultdict(int)
        
        for product_name, quantity in products_to_produce.items():
            product_tasks = products_df[products_df["Product"] == product_name].sort_values(by="Result")
            for unit_idx in range(quantity):
                for _, task_row in product_tasks.iterrows():
                    task_sim_data = task_sim_data_map[task_row["Result"]]
                    instance_counter[task_sim_data.task_id] += 1
                    task_instance = TaskInstance(task_sim_data, instance_counter[task_sim_data.task_id])
                    all_task_instances.append(task_instance)
        
        # Filter tasks for selected products
        all_task_instances = [ti for ti in all_task_instances if ti.product in products_to_produce]

        # Calculate simulation parameters
        total_task_slots = sum(ti.duration_slot for ti in all_task_instances)
        total_worker_slots_per_day = len(available_workers_df) * (8 * 60 / slot_duration_minutes)
        estimated_days = max(1, math.ceil(total_task_slots / total_worker_slots_per_day))
        
        # Simulation state
        current_time_minutes = 0
        max_simulation_time = estimated_days * 8 * 60  # 8 hours per day
        inventory = defaultdict(int)
        partial_completions = []
        
        # Schedule tracking
        schedule = defaultdict(lambda: defaultdict(lambda: defaultdict(str)))
        simulation_log = []
        
        # Main simulation loop
        while current_time_minutes < max_simulation_time:
            current_day = current_time_minutes // (8 * 60) + 1
            current_slot = (current_time_minutes % (8 * 60)) // slot_duration_minutes
            
            # Update worker progress
            for worker_name, worker_data in worker_sim_data_map.items():
                if not worker_data.is_available and worker_data.current_task_instance:
                    worker_data.time_remaining_on_task -= slot_duration_minutes
                    
                    # Update task progress
                    task_instance = worker_data.current_task_instance
                    progress_increment = 100 / task_instance.duration_slot
                    task_instance.progress_percentage = min(100, task_instance.progress_percentage + progress_increment)
                    
                    # Check if task is completed
                    if worker_data.time_remaining_on_task <= 0:
                        task_instance.status = "completed"
                        task_instance.completion_time_minutes = current_time_minutes
                        inventory[task_instance.task_id] += 1
                        
                        worker_data.is_available = True
                        worker_data.current_task_instance = None
                        worker_data.time_remaining_on_task = 0
                        
                        simulation_log.append({
                            "time": format_time(current_time_minutes),
                            "event": f"Worker {worker_name} completed {task_instance.instance_id}"
                        })
            
            # Get available workers and tasks
            available_workers = [w for w in worker_sim_data_map.values() if w.is_available]
            
            # Get earliest tasks (no requirements) and all available tasks
            earliest_tasks = get_earliest_available_tasks(all_task_instances, inventory, partial_completions)
            all_available_tasks = get_available_tasks(all_task_instances, inventory, partial_completions)
            
            # Prioritize tasks for optimal flow
            prioritized_tasks = prioritize_tasks_for_flow(all_available_tasks, earliest_tasks, all_task_instances, inventory, partial_completions)
            
            # Enhanced assignment logic with smart worker distribution
            # Step 1: Identify task progression opportunities
            task_progression_map = {}
            for task in all_available_tasks:
                task_level = len(task.requirements)
                if task_level not in task_progression_map:
                    task_progression_map[task_level] = []
                task_progression_map[task_level].append(task)
            
            # Step 2: Smart worker assignment based on progression strategy
            assigned_workers = set()
            
            # Priority 1: Ensure earliest tasks (level 0) have sufficient workers
            level_0_tasks = task_progression_map.get(0, [])
            if level_0_tasks:
                workers_for_level_0 = max(1, len(available_workers) // 2)  # At least half workers on earliest tasks
                for i, task in enumerate(level_0_tasks[:workers_for_level_0]):
                    if i < len(available_workers):
                        worker = available_workers[i]
                        assign_worker_to_task(worker, task, current_time_minutes, slot_duration_minutes)
                        assigned_workers.add(worker.name)
                        
                        simulation_log.append({
                            "time": format_time(current_time_minutes),
                            "event": f"Worker {worker.name} started {task.instance_id} (earliest task priority)"
                        })
            
            # Priority 2: Assign remaining workers to highest available task level
            remaining_workers = [w for w in available_workers if w.name not in assigned_workers]
            
            # Find highest task level that has available tasks
            max_level = max(task_progression_map.keys()) if task_progression_map else 0
            
            for level in range(max_level, -1, -1):
                if level in task_progression_map and remaining_workers:
                    level_tasks = task_progression_map[level]
                    
                    # Assign workers to this level, but leave some for lower levels if needed
                    if level > 0:
                        # For higher levels, assign fewer workers to maintain balance
                        workers_for_this_level = min(len(remaining_workers) // 2, len(level_tasks))
                    else:
                        # For level 0, assign all remaining workers
                        workers_for_this_level = min(len(remaining_workers), len(level_tasks))
                    
                    for i in range(workers_for_this_level):
                        if i < len(level_tasks) and i < len(remaining_workers):
                            worker = remaining_workers[i]
                            task = level_tasks[i]
                            
                            # Check skill match
                            skill_score = calculate_skill_match(worker.skills, task.skill_requirements)
                            favorite_bonus = 1.2 if task.product in worker.favorite_products else 1.0
                            
                            assign_worker_to_task(worker, task, current_time_minutes, slot_duration_minutes)
                            assigned_workers.add(worker.name)
                            
                            simulation_log.append({
                                "time": format_time(current_time_minutes),
                                "event": f"Worker {worker.name} started {task.instance_id} (level {level}, skill: {skill_score:.2f})"
                            })
                    
                    # Remove assigned workers from remaining list
                    remaining_workers = [w for w in remaining_workers if w.name not in assigned_workers]
            
            # Priority 3: Assign any remaining workers to best available tasks
            remaining_tasks = [t for t in all_available_tasks if t.status == "pending"]
            for worker in remaining_workers:
                if not remaining_tasks:
                    break
                
                # Find best task for this worker based on skill match
                best_task = None
                best_score = 0
                
                for task in remaining_tasks:
                    skill_score = calculate_skill_match(worker.skills, task.skill_requirements)
                    favorite_bonus = 1.2 if task.product in worker.favorite_products else 1.0
                    total_score = skill_score * favorite_bonus
                    
                    if total_score > best_score:
                        best_score = total_score
                        best_task = task
                
                if best_task:
                    assign_worker_to_task(worker, best_task, current_time_minutes, slot_duration_minutes)
                    remaining_tasks.remove(best_task)
                    
                    simulation_log.append({
                        "time": format_time(current_time_minutes),
                        "event": f"Worker {worker.name} started {best_task.instance_id} (fallback assignment)"
                    })
            
            # Record schedule and inventory
            inventory_str = ", ".join([f"{task_id} {count} pcs" for task_id, count in inventory.items() if count > 0])
            if not inventory_str:
                inventory_str = "None, just started"
            
            for worker_name, worker_data in worker_sim_data_map.items():
                if not worker_data.is_available and worker_data.current_task_instance:
                    task_desc = f"[{worker_data.current_task_instance.task_id}] {worker_data.current_task_instance.description}"
                    schedule[current_day][worker_name][current_slot] = task_desc
                else:
                    schedule[current_day][worker_name][current_slot] = "idle"
            
            # Store inventory for this time slot
            schedule[current_day]["Available semi-finished tasks"][current_slot] = inventory_str
            
            # Advance time
            current_time_minutes += slot_duration_minutes
            
            # Check if all tasks are completed
            if all(t.status == "completed" for t in all_task_instances):
                break
        
        return {
            "schedule": schedule,
            "inventory": dict(inventory),
            "simulation_log": simulation_log,
            "estimated_days": estimated_days,
            "all_task_instances": all_task_instances,
            "worker_sim_data_map": worker_sim_data_map
        }
    
    except Exception as e:
        st.error(f"Error in simulation: {str(e)}")
        return None

# --- Display Functions ---
def display_schedule_gantt(schedule_data, estimated_days):
    """Display schedule in simplified Gantt chart format with day tabs"""
    st.subheader("Tasks Schedule")
    
    # Create tabs for each day
    if estimated_days > 0:
        day_tabs = st.tabs([f"Day {day}" for day in range(1, estimated_days + 1)])
        
        for day_idx, day in enumerate(range(1, estimated_days + 1)):
            with day_tabs[day_idx]:
                if day in schedule_data:
                    # Create schedule table
                    day_schedule = schedule_data[day]
                    
                    # Get all time slots
                    all_slots = set()
                    for worker_schedule in day_schedule.values():
                        if isinstance(worker_schedule, dict):
                            all_slots.update(worker_schedule.keys())
                    
                    if all_slots:
                        max_slot = max(all_slots)
                        
                        # Create DataFrame for display
                        schedule_rows = []
                        for slot in range(max_slot + 1):
                            time_str = format_time(slot * 30)
                            row = {"TIME": time_str}
                            
                            # Add worker columns only (no semi-finished column)
                            for worker_name in sorted(day_schedule.keys()):
                                if worker_name != "Available Semi-finished tasks" and isinstance(day_schedule[worker_name], dict):
                                    task_desc = day_schedule[worker_name].get(slot, "idle")
                                    row[f"Worker {worker_name}"] = task_desc
                            
                            schedule_rows.append(row)
                        
                        schedule_df = pd.DataFrame(schedule_rows)
                        
                        # Use container to ensure full width
                        with st.container():
                            st.dataframe(
                                schedule_df, 
                                use_container_width=True,
                                hide_index=True
                            )
                    else:
                        st.info("No schedule for today.")
                else:
                    st.info("No schedule for today.")
    else:
        st.info("No schedule data.")

def display_simulation_results(result):
    """Display simulation results in tabs"""
    if result is None:
        st.error("Simulation failed to be executed!")
        return
    
    st.success(f"Simulation successfull! Estimated time: {result['estimated_days']} days")
    
    # Create tabs without Summary
    tab1, tab2, tab3 = st.tabs(["📅 Schedule", "👥 Worker Stats", "📝 Simulation Log"])
    
    with tab1:
        display_schedule_gantt(result["schedule"], result["estimated_days"])
    
    with tab2:
        st.subheader("Worker Statistics")
        
        worker_stats = []
        for worker_name, worker_data in result["worker_sim_data_map"].items():
            completed_tasks = len([t for t in result["all_task_instances"] if t.assigned_worker_name == worker_name and t.status == "completed"])
            worker_stats.append({
                "Worker": worker_name,
                "Tasks Completed": completed_tasks,
                "Status": "Available" if worker_data.is_available else "Busy"
            })
        
        worker_stats_df = pd.DataFrame(worker_stats)
        st.dataframe(worker_stats_df, use_container_width=True)
    
    with tab3:
        st.subheader("Simulation Log")
        
        if result["simulation_log"]:
            log_df = pd.DataFrame(result["simulation_log"])
            st.dataframe(log_df, use_container_width=True)
        else:
            st.info("No simulation log availableTidak ada log simulasi.")

# --- Main Application ---
def main():
    # Load data
    try:
        workers_df, products_df = load_data()
    except Exception as e:
        st.error(f"Error loading data: {str(e)}")
        return
    
    # Sidebar navigation
    with st.sidebar:
        st.header("Navigation")
        page = st.radio("Go to", ["Home", "Product Database", "Worker Database", "Production Order", "About"])
    
    if page == "Home":
        st.header("Welcome to Worker Task Autoassign System")
        
        st.write("This system helps you organize employee assignments automatically based on:")
        
        st.write("• **Employee expertise** in different type of tasks")
        st.write("• **Dependencies between tasks** in the production process")
        st.write("• **Product preferences** of each employee")
        st.write("• **Dynamic assignment strategies** to maximize efficiency")
        
        # Display summary statistics
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Total Product(s)", len(products_df["Product"].unique()))
        
        with col2:
            st.metric("Total Worker(s)", len(workers_df))
        
        with col3:
            st.metric("Total Type of Task(s)", len(products_df))
        
        st.subheader("Main Features")
        
        st.write("📊 **Product and Worker Database**: View and manage master data")
        st.write("🎯 **Production Order**: Create and manage production orders")
        st.write("📈 **Real-Time Analysis**: View assignment results and performance statistics")
        st.write("🔄 **Dynamic Assignment**: Employees can switch tasks optimally")
    
    elif page == "Product Database":
        st.header("📦 Product Database")
        st.dataframe(products_df, use_container_width=True)
    
    elif page == "Worker Database":
        st.header("👥 Worker Database")
        st.dataframe(workers_df, use_container_width=True)
    
    elif page == "Production Order":
        st.header("🎯 Production Order")
        
        # Product selection and quantity input
        st.subheader("Make a Production Order")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("**Choose Product and Quantity:**")
            
            products_to_produce = {}
            unique_products = products_df["Product"].unique()
            
            for product in unique_products:
                quantity = st.number_input(
                    product, 
                    min_value=0, 
                    max_value=1000, 
                    value=0, 
                    step=1,
                    key=f"qty_{product}"
                )
                if quantity > 0:
                    products_to_produce[product] = quantity
        
        with col2:
            st.write("**Choose Worker(s):**")
            selected_workers = st.multiselect(
                "Choose Worker(s)",
                workers_df["Worker"].tolist(),
                default=workers_df["Worker"].tolist()
            )
        
        # Order summary
        if products_to_produce:
            st.subheader("Order Summary")
            
            for product, qty in products_to_produce.items():
                st.write(f"• **{product}**: {qty} unit(s)")
            
            st.write(f"• **Available worker(s)**: {len(selected_workers)} person(s)")
            
            # Run simulation button
            if st.button("🚀 Run Simulation"):
                if not selected_workers:
                    st.error("Select at least one worker!")
                else:
                    with st.spinner("Running Simulation..."):
                        available_workers_df = workers_df[workers_df["Worker"].isin(selected_workers)]
                        
                        result = assign_tasks(
                            products_to_produce=products_to_produce,
                            available_workers_df=available_workers_df,
                            products_df=products_df,
                            slot_duration_minutes=30
                        )
                        
                        if result:
                            display_simulation_results(result)
    
    elif page == "About":
        st.header("About the System")
        
        st.write("**Task Auto-Assignment System** is an application designed to optimize employee assignments in the production process.")
        
        st.subheader("Key Features:")
        st.write("• Auto-assignment based on skills")
        st.write("• Dependency management between tasks")
        st.write("• Real-time simulation")
        st.write("• Worker performance analysis")
        
        st.subheader("Technology:")
        st.write("• Python & Streamlit")
        st.write("• Pandas for data manipulation")
        st.write("• Assignment optimization algorithm")

if __name__ == "__main__":
    main()

