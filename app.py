import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Import our modules
from db import init_product_db, init_worker_db
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
        
        # Product Orders
        st.subheader("Products")
        
        orders = {}
        col1, col2 = st.columns(2)
        
        with col1:
            for i, product in enumerate(st.session_state.product_db.keys()):
                quantity = st.number_input(f"{product} Quantity", min_value=0, value=0, key=f"prod_{i}")
                orders[product] = quantity
        
        # Worker Availability
        st.subheader("Worker Availability")
        
        worker_availability = []
        with col2:
            for worker_id, worker in st.session_state.worker_db.items():
                if st.checkbox(f"{worker['name']} (ID: {worker_id})", value=True, key=f"worker_{worker_id}"):
                    worker_availability.append(worker_id)
        
        # Generate Schedule Button
        if st.button("Generate Schedule"):
            with st.spinner("Generating production schedule..."):
                result = generate_schedule(
                    orders, 
                    worker_availability, 
                    st.session_state.product_db, 
                    st.session_state.worker_db
                )
                
                if "error" in result:
                    st.error(result["error"])
                else:
                    st.session_state.schedule_result = result
                    st.success(f"Schedule generated! {result['completion_info']['days_needed']} days needed.")
        
        # Display schedule if available
        if 'schedule_result' in st.session_state:
            st.header("Production Schedule")
            
            # Display schedule information
            total_days = st.session_state.schedule_result["completion_info"]["days_needed"]
            st.write(f"Total days needed: {total_days}")
            
            # Display worker roles
            st.subheader("Worker Roles")
            roles_data = []
            for worker_id, role_info in st.session_state.schedule_result["worker_roles"].items():
                roles_data.append({
                    "Worker ID": worker_id,
                    "Name": role_info["name"],
                    "Role": role_info["assigned_role"],
                    "Score": f"{role_info['score']:.2f}"
                })
            
            st.dataframe(pd.DataFrame(roles_data))
            
            # Create Gantt chart
            st.subheader("Production Gantt Chart")
            
            gantt_fig = create_gantt_chart(st.session_state.schedule_result["schedule"])
            if gantt_fig:
                st.plotly_chart(gantt_fig, use_container_width=True)
            
            # Display detailed schedule
            st.subheader("Detailed Schedule")
            
            # Group by day
            schedule_df = pd.DataFrame(st.session_state.schedule_result["schedule"])
            days = schedule_df["day"].unique()
            
            for day in days:
                display_daily_schedule(schedule_df, day)
    
    with tab2:
        st.header("Product Database")
        
        # Display product information
        for product_name, product_data in st.session_state.product_db.items():
            with st.expander(f"{product_name}"):
                # Show product tasks
                task_df = pd.DataFrame(product_data["tasks"])
                st.dataframe(task_df)
                
                # Show tasks attributes visualization
                display_task_attributes(product_data, product_name)
    
    with tab3:
        st.header("Worker Database")
        
        # Display worker information
        for worker_id, worker_data in st.session_state.worker_db.items():
            with st.expander(f"{worker_data['name']} (ID: {worker_id})"):
                # Display worker information
                st.write(f"**Preference:** {worker_data['preference']}")
                
                # Display favorites
                st.write("**Product Preferences:**")
                for i, product in enumerate(worker_data['favorites']):
                    st.write(f"{i+1}. {product}")
                
                # Display skills
                st.subheader("Skills")
                display_worker_skills(worker_data)
                
                # Calculate and display best task matches
                st.subheader("Best Task Matches")
                display_best_task_matches(worker_data, st.session_state.product_db, worker_data['name'])

# Run the main function
if __name__ == "__main__":
    main()
        