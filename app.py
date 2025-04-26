import streamlit as st
from datetime import datetime, timedelta
import uuid
import plotly.express as px
import matplotlib.pyplot as plt
import pandas as pd

# Import local modules
from database import init_product_db_from_csv, init_worker_db
from utils import get_slot_from_time, get_time_from_slot
from scheduler import generate_schedule
from visualization import display_task_attributes, visualize_schedule

# Set page configuration
st.set_page_config(page_title="Task Autoassign System", layout="wide")

# Initialize session state for databases if they don't exist
if 'product_db' not in st.session_state:
    st.session_state.product_db = init_product_db_from_csv("Prototype.csv")

if 'worker_db' not in st.session_state:
    st.session_state.worker_db = init_worker_db()

# Main application UI
def main():
    st.title("Task Auto-assign Production System")
    
    # Sidebar navigation
    st.sidebar.title("Navigation")
    app_mode = st.sidebar.radio(
        "Select Mode",
        ["Home", "Production Planning", "Worker Management", "Product Management"]
    )
    
    # Home screen
    if app_mode == "Home":
        st.header("Welcome to Task Auto-assign Production System")
        st.write("""
        This system helps you optimize your production schedule based on:
        - Worker skills and preferences
        - Product task requirements
        - Order quantities
        
        Use the sidebar to navigate to different sections of the application.
        """)
        
        # Show quick stats
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Total Workers", len(st.session_state.worker_db))
        with col2:
            st.metric("Total Products", len(st.session_state.product_db))
    
    # Production Planning
    elif app_mode == "Production Planning":
        st.header("Production Planning")
        
        # Get all product names
        product_names = list(st.session_state.product_db.keys())
        
        # Product selection using dropdowns
        st.subheader("Select Products for Production")
        
        # Input orders using dropdowns
        orders = {}
        col1, col2, col3 = st.columns(3)
        
        # Allow user to select products from dropdown and specify quantity
        with col1:
            selected_product1 = st.selectbox("Select Product 1", ["None"] + product_names)
            if selected_product1 != "None":
                orders[selected_product1] = st.number_input(f"{selected_product1} quantity", min_value=0, value=1, step=1)
        
        with col2:
            remaining_products = ["None"] + [p for p in product_names if p not in orders.keys()]
            selected_product2 = st.selectbox("Select Product 2", remaining_products)
            if selected_product2 != "None":
                orders[selected_product2] = st.number_input(f"{selected_product2} quantity", min_value=0, value=1, step=1)
        
        with col3:
            remaining_products2 = ["None"] + [p for p in product_names if p not in orders.keys()]
            selected_product3 = st.selectbox("Select Product 3", remaining_products2)
            if selected_product3 != "None":
                orders[selected_product3] = st.number_input(f"{selected_product3} quantity", min_value=0, value=1, step=1)
        
        # Worker availability
        st.subheader("Worker Availability (work hours 08.00-16.00 / 16 slots)")
        
        worker_availability = {}
        cols = st.columns(4)
        
        # Generate all possible time slots between 8:00 and 16:00 with 30-minute intervals
        time_slots = []
        start = datetime.strptime("08:00", "%H:%M")
        end = datetime.strptime("16:00", "%H:%M")
        current = start
        
        while current <= end:
            time_slots.append(current.strftime("%H:%M"))
            current += timedelta(minutes=30)
        
        for i, (worker_id, worker) in enumerate(st.session_state.worker_db.items()):
            col = cols[i % 4]
            with col:
                available = st.checkbox(f"{worker['name']} Available", value=True, key=f"avail_{worker_id}")
                start_time = st.selectbox(
                    f"{worker['name']} Start Time",
                    time_slots,
                    index=0,
                    key=f"start_{worker_id}"
                )
                preference = st.selectbox(
                    f"{worker['name']} Role",
                    ["fixed", "flow"],
                    index=0 if worker['preference'] == 'fixed' else 1,
                    key=f"pref_{worker_id}"
                )
                worker_availability[worker_id] = {
                    "available": available,
                    "start_time": start_time,
                    "preference": preference
                }
        
        # Generate schedule button
        if st.button("Generate Production Schedule"):
            # Check if at least one product is selected
            if not orders:
                st.error("Please select at least one product and specify quantity.")
            else:
                with st.spinner("Generating schedule..."):
                    # Update worker preferences based on current selection
                    for worker_id, availability in worker_availability.items():
                        if worker_id in st.session_state.worker_db:
                            st.session_state.worker_db[worker_id]['preference'] = availability['preference']
                    
                    schedule_result = generate_schedule(
                        orders, 
                        worker_availability, 
                        st.session_state.product_db, 
                        st.session_state.worker_db
                    )
                    
                    # Display schedule statistics
                    if 'stats' in schedule_result:
                        st.subheader("Production Schedule Statistics")
                        col1, col2, col3 = st.columns(3)
                        
                        with col1:
                            st.metric("Total Tasks Assigned", schedule_result['stats']['total_tasks_assigned'])
                        with col2:
                            st.metric("Total Tasks Required", schedule_result['stats']['total_tasks_needed'])
                        with col3:
                            st.metric("Completion Percentage", f"{schedule_result['stats']['completion_percentage']:.1f}%")
                    
                    # Display worker roles
                    if 'worker_roles' in schedule_result:
                        st.subheader("Worker Role Assignments")
                        roles_data = []
                        
                        for worker_id, role_info in schedule_result['worker_roles'].items():
                            roles_data.append({
                                "Worker": role_info['name'],
                                "Assigned Role": role_info['assigned_role'],
                                "Role Score": f"{role_info['score']:.1f}"
                            })
                        
                        st.table(roles_data)
                    
                    # Display unassigned tasks if any
                    if 'unassigned_tasks' in schedule_result and schedule_result['unassigned_tasks']:
                        st.subheader("Unassigned Tasks")
                        st.warning(f"{len(schedule_result['unassigned_tasks'])} tasks could not be assigned.")
                        
                        unassigned_df = pd.DataFrame(schedule_result['unassigned_tasks'])
                        st.dataframe(unassigned_df)
                    
                    # Display schedule visualization
                    visualize_schedule(schedule_result)
    
    # Worker Management
    elif app_mode == "Worker Management":
        from worker_management import display_worker_management
        display_worker_management()
    
    # Product Management
    elif app_mode == "Product Management":
        from product_management import display_product_management
        display_product_management()

if __name__ == "__main__":
    main()