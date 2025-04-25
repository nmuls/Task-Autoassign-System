import pandas as pd
import plotly.express as px
import streamlit as st
from datetime import datetime, timedelta

def display_worker_skills(worker_data):
    """Display worker skills as radar chart and bar chart"""
    # Convert skills to DataFrame
    skills_df = pd.DataFrame({
        "Skill": list(worker_data["skills"].keys()),
        "Value": list(worker_data["skills"].values())
    })
    
    # Display as table and chart
    col1, col2 = st.columns(2)
    
    with col1:
        st.dataframe(skills_df.sort_values("Value", ascending=False))
    
    with col2:
        fig = px.bar(
            skills_df.sort_values("Value"),
            x="Value",
            y="Skill",
            orientation='h',
            title=f"{worker_data['name']}'s Skills"
        )
        st.plotly_chart(fig, use_container_width=True)
    
    # Display skills as radar chart
    fig = px.line_polar(
        skills_df,
        r="Value",
        theta="Skill",
        line_close=True,
        title=f"{worker_data['name']}'s Skills Radar"
    )
    fig.update_polars(radialaxis=dict(visible=True, range=[0, 100]))
    st.plotly_chart(fig, use_container_width=True)

def display_best_task_matches(worker_data, product_db, worker_name):
    """Display best task matches for a worker"""
    # Calculate match scores for all product tasks
    from system import calculate_worker_task_match
    
    best_matches = []
    for product, product_info in product_db.items():
        for task in product_info['tasks']:
            match_score = calculate_worker_task_match(worker_data, task)
            best_matches.append({
                'Product': product,
                'Task': task['name'],
                'Match Score': match_score
            })
    
    # Display top 5 best matches
    best_matches_df = pd.DataFrame(best_matches).sort_values('Match Score', ascending=False).head(5)
    st.dataframe(best_matches_df)
    
    # Create bar chart for best matches
    fig = px.bar(
        best_matches_df,
        x='Match Score',
        y='Task',
        color='Product',
        title=f"Top 5 Task Matches for {worker_name}",
        orientation='h'
    )
    st.plotly_chart(fig, use_container_width=True)

def display_task_attributes(product_data, product_name):
    """Display task attributes for a product"""
    st.subheader("Task Attributes")
    
    # Prepare data for radar chart
    task_attributes = {}
    for task in product_data["tasks"]:
        attributes = task["attributes"]
        task_attributes[task["name"]] = attributes
    
    # Create a radar chart for each task's attributes
    for task_name, attributes in task_attributes.items():
        df_attr = pd.DataFrame({
            "Attribute": list(attributes.keys()),
            "Value": list(attributes.values())
        })
        
        fig = px.line_polar(
            df_attr,
            r="Value",
            theta="Attribute",
            line_close=True,
            title=f"{task_name} Attributes"
        )
        fig.update_polars(radialaxis=dict(visible=True, range=[0, 100]))
        st.plotly_chart(fig, use_container_width=True)

def create_gantt_chart(schedule_data):
    """Create a Gantt chart visualization of the schedule"""
    gantt_data = []
    
    for entry in schedule_data:
        if entry["task_id"] is not None:  # Skip idle slots
            start_time = datetime.strptime(f"Day {entry['day']} {entry['time']}", "Day %d %H:%M")
            
            # Find end time based on task duration
            # For simplicity, assuming all tasks are 30 min blocks
            end_time = start_time + timedelta(minutes=30)
            
            gantt_data.append({
                "Task": f"{entry['product']} - {entry['task_name']}",
                "Start": start_time,
                "Finish": end_time,
                "Resource": entry["worker_name"],
                "Worker Role": entry["worker_role"],
                "Task Role": entry["task_role"]
            })
    
    if gantt_data:
        df_gantt = pd.DataFrame(gantt_data)
        
        # Create custom color map for worker roles
        color_map = {"fixed": "blue", "flow": "green", "rebalanced": "orange"}
        
        fig = px.timeline(
            df_gantt, 
            x_start="Start", 
            x_end="Finish", 
            y="Resource", 
            color="Task",
            hover_data=["Worker Role", "Task Role"],
            title="Production Schedule Gantt Chart"
        )
        
        fig.update_layout(
            xaxis_title="Time",
            yaxis_title="Worker"
        )
        
        return fig
    
    return None

def display_daily_schedule(schedule_df, day):
    """Display detailed schedule for a specific day"""
    day_data = schedule_df[schedule_df["day"] == day]
    
    with st.expander(f"Day {day}"):
        # Pivot the data to create a timetable
        pivot_df = day_data.pivot(index=["worker_name", "worker_id"], columns="time", values="task_name")
        st.dataframe(pivot_df, use_container_width=True)
        
        # Count task distribution
        task_counts = day_data[day_data["task_id"].notnull()].groupby(["worker_name", "product", "task_name"]).size().reset_index(name="count")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Task Distribution")
            st.dataframe(task_counts)
        
        with col2:
            # Calculate idle time percentage
            idle_counts = day_data.groupby("worker_name")["status"].apply(lambda x: (x == "idle").mean() * 100).reset_index()
            idle_counts.columns = ["Worker", "Idle Time (%)"]
            
            st.subheader("Idle Time")
            st.dataframe(idle_counts)
            
            # Create a bar chart for idle time
            fig = px.bar(
                idle_counts,
                x="Worker",
                y="Idle Time (%)",
                title="Worker Idle Time Percentage"
            )
            st.plotly_chart(fig, use_container_width=True)