import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, time
# Import our modules
from db import init_product_db, init_worker_db, get_all_tasks_for_production
from system import generate_schedule, calculate_worker_task_match
from visualization import (
    display_worker_skills, 
    display_best_task_matches, 
    display_task_attributes, 
    create_gantt_chart,
    display_daily_schedule
)
# Set page configuration
st.set_page_config(page_title="Task Autoassign System", layout="wide")
# Initialize session state for databases if they don't exist
if 'product_db' not in st.session_state:
    st.session_state.product_db = init_product_db()
if 'worker_db' not in st.session_state:
    st.session_state.worker_db = init_worker_db()
def main():
    st.title("Task Autoassign System")
    
    tab1, tab2, tab3 = st.tabs(["Production Order", "Product Database", "Worker Database"])
    
    with tab1:
        st.header("Production Order Input")
        
        # Product Orders with Dropdown
        st.subheader("Select Products")
        
        orders = {}
        col1, col2 = st.columns(2)
        
        with col1:
            # List available products
            available_products = list(st.session_state.product_db.keys())
            
            # Create form for product selection
            with st.form("product_form"):
                # Create a dropdown to select products
                selected_product = st.selectbox(
                    "Select a product to manufacture",
                    available_products
                )
                
                # Set quantity for selected product
                quantity = st.number_input(f"{selected_product} Quantity", min_value=0, value=1)
                
                # Add product button
                submit_button = st.form_submit_button("Add Product")
            
            # Initialize or get orders from session state
            if 'orders' not in st.session_state:
                st.session_state.orders = {}
            
            # Add product to orders when form is submitted
            if submit_button:
                if selected_product in st.session_state.orders:
                    st.session_state.orders[selected_product] += quantity
                else:
                    st.session_state.orders[selected_product] = quantity
                st.success(f"Added {quantity} x {selected_product}")
            
            # Display the selected products and quantities
            st.subheader("Selected Products")
            
            if not st.session_state.orders:
                st.info("No products selected yet")
            else:
                for product, qty in st.session_state.orders.items():
                    st.write(f"{product}: {qty}")
                
                # Allow clearing all products
                if st.button("Clear All Products"):
                    st.session_state.orders = {}
                    st.experimental_rerun()
        
        with col2:
            # Scheduling parameters
            st.subheader("Scheduling Parameters")
            
            # Date and time selection
            start_date = st.date_input("Start Date", datetime.now().date())
            
            # Working hours
            st.write("Working Hours")
            start_time = st.time_input("Start Time", time(8, 0))
            end_time = st.time_input("End Time", time(17, 0))
            
            # Workers selection
            st.subheader("Available Workers")
            
            all_workers = list(st.session_state.worker_db.keys())
            selected_workers = st.multiselect("Select Workers", all_workers, default=all_workers)
            
            # Generate schedule button
            if st.button("Generate Schedule"):
                if not st.session_state.orders:
                    st.error("Please add at least one product to the order.")
                elif not selected_workers:
                    st.error("Please select at least one worker.")
                else:
                    # Get all tasks required for the selected products
                    all_tasks = get_all_tasks_for_production(st.session_state.orders, st.session_state.product_db)
                    
                    # Calculate worker-task matches
                    worker_task_matches = {}
                    for worker_name in selected_workers:
                        worker = st.session_state.worker_db[worker_name]
                        worker_task_matches[worker_name] = {
                            task_id: calculate_worker_task_match(worker, task)
                            for task_id, task in all_tasks.items()
                        }
                    
                    # Generate schedule
                    schedule_start = datetime.combine(start_date, start_time)
                    schedule_end = datetime.combine(start_date, end_time)
                    
                    schedule = generate_schedule(
                        all_tasks, 
                        {name: st.session_state.worker_db[name] for name in selected_workers},
                        worker_task_matches,
                        schedule_start,
                        schedule_end
                    )
                    
                    # Store results in session state
                    st.session_state.all_tasks = all_tasks
                    st.session_state.worker_task_matches = worker_task_matches
                    st.session_state.schedule = schedule
                    
                    st.success("Schedule generated successfully!")
        
        # Display schedule if it exists
        if 'schedule' in st.session_state:
            st.header("Generated Schedule")
            
            # Create tabs for different schedule views
            schedule_tab1, schedule_tab2, schedule_tab3 = st.tabs(["Gantt Chart", "Daily Schedule", "Worker Assignments"])
            
            with schedule_tab1:
                # Display Gantt chart
                gantt_chart = create_gantt_chart(st.session_state.schedule, st.session_state.all_tasks)
                st.plotly_chart(gantt_chart, use_container_width=True)
            
            with schedule_tab2:
                # Display daily schedule
                display_daily_schedule(st.session_state.schedule, st.session_state.all_tasks)
            
            with schedule_tab3:
                # Display worker assignments
                for worker_name in selected_workers:
                    st.subheader(f"Tasks for {worker_name}")
                    worker_tasks = [task for task in st.session_state.schedule if task['worker'] == worker_name]
                    if worker_tasks:
                        worker_df = pd.DataFrame(worker_tasks)
                        worker_df['task_name'] = worker_df['task_id'].apply(lambda x: st.session_state.all_tasks[x]['name'])
                        worker_df = worker_df[['task_name', 'start_time', 'end_time']]
                        worker_df = worker_df.sort_values('start_time')
                        st.dataframe(worker_df)
                    else:
                        st.info(f"No tasks assigned to {worker_name}")
    
    with tab2:
        st.header("Product Database")
        
        # Display products and their tasks
        for product_name, product_data in st.session_state.product_db.items():
            with st.expander(f"{product_name}"):
                # Check if description exists before displaying it
                if 'description' in product_data:
                    st.write(f"Description: {product_data['description']}")
                else:
                    st.write("Description: Not available")
                
                # Display tasks for this product
                st.subheader("Required Tasks")
                tasks_df = pd.DataFrame(product_data['tasks'])
                st.dataframe(tasks_df)
                
                # Display task attributes visualization
                # Pass the product_name as well as the tasks
                display_task_attributes(product_data['tasks'], product_name)
    
    with tab3:
        st.header("Worker Database")
        
        # Display workers and their skills
        col1, col2 = st.columns(2)
        
        with col1:
            # Let user select a worker to view details
            selected_worker = st.selectbox(
                "Select a worker to view details",
                list(st.session_state.worker_db.keys())
            )
            
            worker_data = st.session_state.worker_db[selected_worker]
            
            st.subheader(f"{selected_worker}'s Profile")
            st.write(f"Role: {worker_data['role']}")
            st.write(f"Experience: {worker_data['experience']} years")
            
            # Display worker skills visualization
            display_worker_skills(worker_data)
        
        with col2:
            if 'all_tasks' in st.session_state:
                st.subheader("Best Task Matches")
                display_best_task_matches(
                    selected_worker,
                    st.session_state.worker_db[selected_worker],
                    st.session_state.all_tasks,
                    st.session_state.worker_task_matches[selected_worker]
                )
            else:
                st.info("Generate a schedule to see task match recommendations")

if __name__ == "__main__":
    main()