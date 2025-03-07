import streamlit as st
import pandas as pd
import re
from datetime import time, datetime
import requests

# Time slot mapping with numeric column references for courses
COURSE_TIME_SLOTS = {
    "8:30-10:00": [1, 2, 3],
    "10:00-11:20": [4, 5, 6], 
    "11:30-12:50": [7, 8, 9], 
    "1:00-2:20": [10, 11, 12], 
    "2:30-3:50": [13, 14, 15], 
    "4:00-5:20": [16, 17, 18]  
}

# Lab time slot mapping with numeric column references
LAB_TIME_SLOTS = {
    "8:30-11:15": [ 1,2, 3, 4, 5, 6],
    "11:25-2:10": [ 7, 8, 9 ,10,11],
    "2:25-5:10": [12, 13, 14, 15, 16]   
}

# Mapping for days and their corresponding Google Sheets URLs
DAY_MAPPING = {
    "Monday": "https://docs.google.com/spreadsheets/d/1dk0Raaf9gtbSdoMAGZal3y4m1kwr7UiuulxFxDKpM8Q/export?format=xlsx&gid=1882612924",
    "Tuesday": "https://docs.google.com/spreadsheets/d/1dk0Raaf9gtbSdoMAGZal3y4m1kwr7UiuulxFxDKpM8Q/export?format=xlsx&gid=2125644028",
    "Wednesday": "https://docs.google.com/spreadsheets/d/1dk0Raaf9gtbSdoMAGZal3y4m1kwr7UiuulxFxDKpM8Q/export?format=xlsx&gid=1029559174",
    "Thursday": "https://docs.google.com/spreadsheets/d/1dk0Raaf9gtbSdoMAGZal3y4m1kwr7UiuulxFxDKpM8Q/export?format=xlsx&gid=191320255",
    "Friday": "https://docs.google.com/spreadsheets/d/1dk0Raaf9gtbSdoMAGZal3y4m1kwr7UiuulxFxDKpM8Q/export?format=xlsx&gid=1783333514"
}

def download_sheet(url):
    """
    Download the Excel sheet from the given URL
    
    :param url: Google Sheets export URL
    :return: pandas DataFrame of the sheet
    """
    try:
        response = requests.get(url)
        response.raise_for_status()  # Raise an exception for bad status codes
        return pd.read_excel(response.content)
    except Exception as e:
        st.error(f"Error downloading sheet: {e}")
        return None

def categorize_classroom_by_block(classroom_name):
    """
    Categorize classroom by its building block (A, B, C, etc.)
    Handle special cases like Rawal labs and generic Lab entries
    Ignore 'nan' values
    
    :param classroom_name: String name of the classroom
    :return: Block identifier (A, B, C, etc.) or "Other" or None to skip
    """
    # Convert to string and clean
    classroom_str = str(classroom_name).strip()
    
    # Ignore 'nan' values
    if classroom_str.lower() == 'nan' or not classroom_str:
        return None  # Will be filtered out later
    
    # Special case for Rawal labs (they are in B block)
    if "rawal" in classroom_str.lower():
        return "B"
    
    # Skip generic "Lab" entries that aren't associated with a specific block
    if classroom_str.lower() == "lab":
        return None  # Skip these entries
    
    # Regular case: extract first letter if it's alphabetic
    if classroom_str and len(classroom_str) > 0 and classroom_str[0].isalpha():
        return classroom_str[0]
    
    return "Other"
    
def load_sheet(sheet_url):
    df = pd.read_excel(sheet_url, header=None)
    
    # Check day in cell A1
    day_cell = df.iloc[0, 0]  # A1 cell (row 0, column 0)
    is_tuesday_or_thursday = "Tuesday" in str(day_cell) or "Thursday" in str(day_cell)
    
    timetable_start_index = None
    for index, row in df.iterrows():
        if "Room" in row.values:
            timetable_start_index = index
            break
    
    batch_rows = df.iloc[:4].values.tolist()
    
    if timetable_start_index is not None:
        # Get regular class data
        
        regular_data = df.iloc[timetable_start_index:timetable_start_index+43-5].reset_index(drop=True).values.tolist()
        
        if is_tuesday_or_thursday:
            # Lab timings row and lab data for Tuesday and Thursday
            lab_timings_row = df.iloc[timetable_start_index+42-5].values.tolist()
            lab_data = df.iloc[timetable_start_index+42-5:].reset_index(drop=True).values.tolist()
        else:
            # Lab timings row and lab data for other days
            lab_timings_row = df.iloc[timetable_start_index+43-5].values.tolist()
            lab_data = df.iloc[timetable_start_index+43-5:].reset_index(drop=True).values.tolist()
        
        # Insert lab timings as the first row of lab_data
        lab_data.insert(0, lab_timings_row)
    else:
        regular_data = []
        lab_data = []
    
    return batch_rows, regular_data, lab_data

def is_valid_course(text):
    pattern = r"^[A-Za-z0-9\s]+ \([A-Za-z0-9-]+\)(?:\s+.*)?$"
    return bool(re.match(pattern, text))

def extract_department_from_course(course_str):
    """Extract department code from course string"""
    if not course_str or not isinstance(course_str, str):
        return ""
    
    # Try to extract department code like CS, SE, DS, etc. from course code
    match = re.search(r"\(([A-Za-z]{2})-", course_str)
    if match:
        return match.group(1)
    return ""

def extract_custom_time(course_str):
    """Extract custom time if it exists in the course string"""
    if not course_str or not isinstance(course_str, str):
        return None
    
    # Pattern to match time formats like "1:00-3:00" or "1:00 - 3:00"
    pattern = r"(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})"
    match = re.search(pattern, course_str)
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    return None

def extract_standard_time_slots(regular_data, lab_data=None):
    """
    Extract standard time slots from regular and lab data, removing non-standard entries
    """
    time_slots = []
    standard_time_pattern = r'^\d{2}:\d{2}-\d{2}:\d{2}$'
    
    # Extract from regular data
    if regular_data and len(regular_data) > 0:
        for time_slot in regular_data[0][1:]:  # Skip first column (room)
            if isinstance(time_slot, str) and re.match(standard_time_pattern, time_slot.strip()):
                time_slots.append(time_slot.strip())
    
    # Extract from lab data
    if lab_data and len(lab_data) > 0:
        for time_slot in lab_data[0][1:]:  # Skip first column (room)
            if isinstance(time_slot, str) and re.match(standard_time_pattern, time_slot.strip()):
                if time_slot.strip() not in time_slots:
                    time_slots.append(time_slot.strip())
    
    return sorted(time_slots)

def find_free_classes(df, time_slot_columns, search_type):
    """
    Find free classes for specific time slot columns
    
    :param df: DataFrame containing the timetable
    :param time_slot_columns: List of column indices to check
    :param search_type: 'course' or 'lab'
    :return: List of free classes
    """
    free_classes = []
    
    # Set row range based on search type
    if search_type == 'course':
        start_row, end_row = 1, 42  # Theory classes from rows 1-42
    elif search_type == 'lab':
        start_row, end_row = 43, df.shape[0]  # Lab classes from row 43 onwards
    else:
        st.error("Invalid search type")
        return []
    
    # Check specified rows for courses or labs
    for row in range(start_row, end_row):
        if row >= df.shape[0]:  # Safety check to avoid index errors
            break
            
        row_data = df.iloc[row]
        
        # Check if the classroom is empty for ALL specified time slot columns
        is_free = all(pd.isna(row_data[col]) for col in time_slot_columns)
        
        # Additional check to ensure no data in the time slot columns
        if is_free:
            # Get classroom from Column A
            classroom = row_data[0]
            
            free_classes.append({
                'row': row,
                'classroom': classroom
            })
    
    return free_classes

def find_empty_rooms(selected_day, selected_time, DAY_MAPPING):
    """Find empty rooms for the selected day and time slot"""
    sheet_url = DAY_MAPPING[selected_day]
    _, regular_data, lab_data = load_sheet(sheet_url)
    
    # Get all rooms
    all_rooms = set()
    occupied_rooms = set()
    
    # Process regular classes and labs
    data_sets = [
        (regular_data, regular_data[0], 1, 42),  # Regular class data with its time row and row range
        (lab_data, lab_data[0] if lab_data else [], 43, len(lab_data))  # Lab data with its time row and row range
    ]
    
    for data, time_row, start_row_idx, end_row_idx in data_sets:
        # Find the column index for the selected time
        try:
            target_col_index = time_row.index(selected_time)
        except ValueError:
            continue  # Skip if time not found
        
        # Use the specified row range
        for row_idx in range(start_row_idx, end_row_idx):
            if row_idx >= len(data):  # Safety check
                continue
                
            row = data[row_idx]
            
            # Ensure row has enough columns
            if len(row) <= target_col_index:
                continue
            
            room = str(row[0]).strip()
            if room and room != "nan":
                all_rooms.add(room)
                
                # Check if room is occupied
                cell_content = str(row[target_col_index]).strip()
                if cell_content and cell_content != "nan" and is_valid_course(cell_content):
                    occupied_rooms.add(room)
    
    # Get empty rooms
    empty_rooms = sorted(list(all_rooms - occupied_rooms))
    
    return empty_rooms
    
def main():
    st.set_page_config(page_title="Academic Schedule Lookup", layout="wide")
    
    # Wrap the title and button in one flex container
    st.markdown("""
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
        <div class="main-title" style="margin: 0;">
            FAST NUCES TIMETABLE
        </div>
        <a href="https://www.linkedin.com/in/sidhart-sami-9a2051296/" target="_blank" style="
            display: inline-block;
            background-color: #FFD700;
            color: #000;
            padding: 0.5rem 1rem;
            border-radius: 4px;
            text-decoration: none;
            font-weight: bold;
        ">
            Developer
        </a>
    </div>
    """, unsafe_allow_html=True)
    
    
    st.markdown("""
    <style>
    /* Overall page background & text */
    .stApp {
        background-color: #FFFFFF; /* White background */
        color: #000000; /* Black text */
    }

    /* Main title */
    .main-title {
    font-size: 32px;           /* Large, prominent text */
    font-weight: 800;         /* Extra bold */
    margin-bottom: 20px;
    color: #FFD700;           /* Bright yellow text */
    text-transform: uppercase; /* All caps */
    letter-spacing: 1px;      /* Spaced letters */
    border-bottom: 2px solid #FFD700; /* Title line */
    padding-bottom: 8px;      /* Space above the line */
    }

    /* Cards */
    .card {
        border: 1px solid #DDDDDD;
        border-radius: 5px;
        padding: 15px;
        margin-bottom: 10px;
        background-color: #FFFFFF; /* White card */
        color: #000000; /* Black text */
        transition: 0.3s;
    }
    .card:hover {
        transform: translateY(-3px);
    }

    /* Card Title */
    .card-title {
        font-weight: bold;
        margin-bottom: 10px;
        font-size: 24px;
        color: black; /* Distinguish title text in card */
    }

    /* Lab, Regular, Special side lines */
    .lab-card {
        border-left: 8px solid #FFD700; /* Yellow for Labs */
    }
    .regular-card {
    border-left: 8px solid #FFA500; /* Orange for Regular */
    }

    .special-card {
        border-left: 8px solid #ec407a;
        background-color: #fde6ec; /* Lighter pink for Special */
    }

    /* Card details */
    .card-details {
        color: #333333; /* Darker text for readability */
        font-size: 14px;
    }

    .my-class-indicator {
    background-color: #eaeaea;
    color: #FFD700;
    font-size: 12px;
    padding: 2px 6px;
    border-radius: 3px;
    display: inline-block;
    margin-left: 8px; /* Add some spacing between course name and indicator */
    vertical-align: middle;
    }


    /* Subheader for sections */
    .subheader {
        font-size: 20px;
        font-weight: 500;
        margin: 20px 0 10px 0;
        color: #FFD700;
    }

    /* Filter container background & text */
    .filter-container {
        background-color: #f5f5f5; /* Light gray container */
        color: #000000;
        padding: 15px;
        border-radius: 5px;
        margin-bottom: 20px;
    }

    /* Professor info */
    .professor-info {
        font-style: italic;
        margin-top: 5px;
        color: #666666;
    }

    /* Class type badge */
    .class-type {
        display: inline-block;
        margin-left: 8px;
        font-size: 12px;
        padding: 1px 5px;
        border-radius: 3px;
        background-color: #eaeaea;
        color: #333333;
    }

    /* Current day info box */
    .current-day-info {
        background-color: #fff9cc; /* Light yellow highlight */
        padding: 10px 15px;
        border-radius: 5px;
        margin-bottom: 15px;
        color: #000000;
        font-weight: 500;
    }

    /* Empty room card */
    .empty-room-card {
        border-left: 4px solid #808000;
        background-color: #f9f9f9;
    }

    /* Buttons */
    .stButton>button {
        background-color: #FFD700;
        color: #000000;
        border: none;
        border-radius: 4px;
        padding: 0.375rem 0.75rem;
        font-size: 1rem;
        font-weight: 400;
        transition: background-color 0.3s;
    }
    .stButton>button:hover {
        background-color: #D4B200; /* Darker gold on hover */
    }

    /* Footer */
    footer {
        text-align: center;
        margin-top: 30px;
        padding-top: 10px;
        border-top: 1px solid #DDDDDD;
        color: #666666;
        font-size: 12px;
    }

    
    </style>
""", unsafe_allow_html=True)
    
    # Get current day
    current_day = datetime.now().strftime("%A")
    
    # If today is Saturday or Sunday, default to Monday
    if current_day in ["Saturday", "Sunday"]:
        default_day = "Monday"
        is_weekend = True
    else:
        default_day = current_day
        is_weekend = False
    
    # Add tabs to navigate between Schedule and Empty Rooms features
    tab1, tab2 = st.tabs(["Class Schedule", "Find Empty Rooms"])
    
    with tab1:
    # Initialize session state for my_classes_list if not present.
        if "my_classes_list" not in st.session_state:
            st.session_state.my_classes_list = []
        # Also initialize a flag to show success message.
        if "show_success" not in st.session_state:
            st.session_state.show_success = False

        # My Classes Section
        with st.expander("Add/Manage My Classes", expanded=True):
            @st.cache_data(ttl=300)
            def gather_all_classes(DAY_MAPPING):
                all_classes = set()
                for sheet_url in DAY_MAPPING.values():
                    _, regular_data, lab_data = load_sheet(sheet_url)
                    for data in [regular_data, lab_data]:
                        for row in data[6:]:
                            for cell in row:
                                cell_str = str(cell).strip()
                                if cell_str and is_valid_course(cell_str):
                                    all_classes.add(cell_str)
                return sorted(all_classes)

            all_classes = gather_all_classes(DAY_MAPPING)
            valid_defaults = [c for c in st.session_state.my_classes_list if c in all_classes]
            
            # Place the multiselect and button in two columns
            cols = st.columns([3, 1])
            with cols[0]:
                chosen = st.multiselect(
                    "Select your classes:", 
                    options=all_classes, 
                    default=valid_defaults,
                    placeholder="Choose your classes..."
                )
            with cols[1]:
                st.write("")  # Spacer to align the button
                st.write("")
                if st.button("Save Classes"):
                    st.session_state.my_classes_list = chosen
                    st.session_state.show_success = True

        # Place the success message outside the columns for full width display.
        if st.session_state.show_success:
            st.success("Classes saved successfully!")
            st.session_state.show_success = False  # Reset the flag

        st.divider()

        # Filters Section
        st.markdown('<div class="subheader">Filter Options</div>', unsafe_allow_html=True)
        with st.container():
            st.markdown('<div class="filter-container">', unsafe_allow_html=True)
            cols = st.columns([1, 1, 2])
            with cols[0]:
                default_day_index = list(DAY_MAPPING.keys()).index(default_day)
                selected_day = st.selectbox("Select Day", list(DAY_MAPPING.keys()), index=default_day_index, key="schedule_day")
            with cols[1]:
                sheet_url = DAY_MAPPING[selected_day]
                batch_rows, regular_data, lab_data = load_sheet(sheet_url)
                department_options = [
                    "All", 
                    "CS - Computer Science", 
                    "DS - Data Science", 
                    "AI - Artificial Intelligence", 
                    "CY - Cyber Security", 
                    "SE - Software Engineering",
                    "MS-CS - Master of Computer Science",
                    "MS-DS - Master of Data Science",
                    "MS-AI - Master of Artificial Intelligence",
                    "MS-CY - Master of Cyber Security",
                    "MS-SE - Master of Software Engineering"
                ]
                selected_department = st.selectbox("Select Department", department_options)
                selected_department_code = selected_department.split(" - ")[0] if " - " in selected_department else selected_department
            with cols[2]:
                search_query = st.text_input("Search Course:", placeholder="Type course name or code...")
            
            cols = st.columns([2, 2])
            with cols[0]:
                content_type = st.radio("Show:", ["All", "Regular Classes", "Labs Only"], horizontal=True)
            with cols[1]:
                my_classes_on = st.checkbox("Show Only My Classes", value=False)
            st.markdown('</div>', unsafe_allow_html=True)

        # Processing logic: gather and display results
        found_results = []
        if content_type in ["All", "Regular Classes"]:
            for row in regular_data[6:]:
                for col_index in range(len(row)):
                    if col_index == 0: continue  # Skip room column
                    cell_str = str(row[col_index]).strip()
                    if process_cell(cell_str, search_query, my_classes_on, selected_department_code):
                        room = row[0] if row else "N/A"
                        default_time = regular_data[0][col_index] if regular_data and len(regular_data[0]) > col_index else "N/A"
                        custom_time = extract_custom_time(cell_str)
                        display_time = custom_time if custom_time else default_time
                        found_results.append(create_card(
                            cell_str, room, display_time, 
                            is_lab=False,
                            is_my_class=any(my_class in cell_str for my_class in st.session_state.my_classes_list)
                        ))
        if content_type in ["All", "Labs Only"] and lab_data:
            for row_index, row in enumerate(lab_data[1:], 1):
                for col_index in range(len(row)):
                    if col_index == 0: continue
                    cell_str = str(row[col_index]).strip()
                    if process_cell(cell_str, search_query, my_classes_on, selected_department_code):
                        room = row[0] if row else "N/A"
                        default_time = lab_data[0][col_index] if lab_data and len(lab_data[0]) > col_index else "N/A"
                        custom_time = extract_custom_time(cell_str)
                        display_time = custom_time if custom_time else default_time
                        found_results.append(create_card(
                            cell_str, room, display_time,
                            is_lab=True,
                            is_my_class=any(my_class in cell_str for my_class in st.session_state.my_classes_list)
                        ))
        if found_results:
            st.markdown(f'<div class="subheader">Results ({len(found_results)} found)</div>', unsafe_allow_html=True)
            for result in found_results:
                card_class = "lab-card" if result['is_lab'] else "regular-card"
                if result.get('special'):
                    card_class = "special-card"
                my_class_indicator = '<span class="my-class-indicator">My Class</span>' if result['is_my_class'] else ''
                class_type_display = '<span class="class-type">Lab</span>' if result['is_lab'] else ''
                professor_info = ""
                if 'class' in result and isinstance(result['class'], str):
                    display_course = re.sub(r"\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2}", "", result['class']).strip()
                    prof_match = re.search(r"\)\s+(.+?)$", display_course)
                    if prof_match:
                        professor = prof_match.group(1).strip()
                        professor_info = f'<div class="professor-info">Instruction: {professor}</div>'
                st.markdown(f"""
                    <div class="card {card_class}">
                        <div class="card-title">{result['class']} {my_class_indicator} {class_type_display}</div>
                        <div class="card-details">
                            <strong>Time:</strong> {result['time']} | <strong>Room:</strong> {result['room']}
                        </div>
                        {professor_info}
                    </div>
                """, unsafe_allow_html=True)
        else:
            handle_empty_results(my_classes_on, search_query, selected_day, selected_department_code)

    # Empty Rooms Tab
    # Modified code section for the empty rooms tab with centered boxes
    # Modified code section with fix for non-subscriptable classroom names
    with tab2:
        st.markdown('<div class="subheader">Find Empty Rooms</div>', unsafe_allow_html=True)
        
        with st.container():
            st.markdown('<div class="filter-container">', unsafe_allow_html=True)
            col1, col2, col3 = st.columns(3)

            # Day selection
            with col1:
                selected_day = st.selectbox("Select a Day", list(DAY_MAPPING.keys()))
            
            # Search type selection
            with col2:
                search_type = st.selectbox("Search Type", ['course', 'lab'])
            
            # Time slot selection based on search type
            with col3:
                if search_type == 'course':
                    selected_time_slot = st.selectbox("Select Time Slot", list(COURSE_TIME_SLOTS.keys()))
                    time_slots_dict = COURSE_TIME_SLOTS
                else:
                    selected_time_slot = st.selectbox("Select Time Slot", list(LAB_TIME_SLOTS.keys()))
                    time_slots_dict = LAB_TIME_SLOTS
            
            # Find button with full width
            if st.button("Find Free Classrooms", use_container_width=True):
                # Download the sheet for the selected day
                if selected_day == "Friday" and selected_time_slot == "1:00-2:20":
                    st.markdown(namaz_break_card(), unsafe_allow_html=True)
                else:
                    df = download_sheet(DAY_MAPPING[selected_day])
                    
                    if df is not None:
                        # Get columns for the selected time slot
                        time_slot_columns = time_slots_dict[selected_time_slot]
                        
                        # Find free classes
                        free_classes = find_free_classes(df, time_slot_columns, search_type)
                        
                        # Display results
                        if free_classes:
                            st.success(f"Free {search_type.capitalize()} Classrooms on {selected_day} during {selected_time_slot}")
                            st.markdown("""                            
                            <style>
                                .building-section {
                                    margin-bottom: 30px; /* Increased section margin */
                                }

                                .building-title {
                                    font-size: 1.6rem; /* Increased from 1.2rem */
                                    font-weight: 700; /* Bolder than before (was 500) */
                                    margin-bottom: 20px; /* More space below title */
                                    color: #FFD700;      /* Yellow to match main theme */
                                    letter-spacing: 0.5px; /* Slightly spread letters for emphasis */
                                }

                                .classroom-box {
                                    border: none;  /* Remove the full border */
                                    border-left: 8px solid #FFA500;  /* Olive green border on the left only */
                                    border-radius: 10px;
                                    padding: 15px;
                                    background-color: #FFFFFF;   /* White background */
                                    text-align: center;
                                    width: 180px;
                                    height: 140px;
                                    display: flex;
                                    flex-direction: column;
                                    justify-content: center;
                                    align-items: center;
                                    box-shadow: 0 2px 5px rgba(0,0,0,0.1);
                                    float: left;
                                    margin-right: 25px; /* Keep horizontal spacing */
                                    margin-bottom: 80px; /* Increased from 25px to 40px for more vertical space */
                                }

                                .classroom-row {
                                    display: flex;
                                    flex-wrap: wrap;
                                    gap: 25px 25px; /* First value controls row gap, second controls column gap */
                                    margin-bottom: 40px; /* Increased bottom margin of rows */
                                }

                                .classroom-name {
                                    color: black;         /* Olive green text */
                                    font-size: 1.5rem;
                                    font-weight: bold;
                                    margin-bottom: 8px;
                                }

                                .classroom-detail {
                                    color: #555555;         /* Dark gray for better contrast */
                                    font-size: 0.9rem;
                                }

                                .classroom-emoji {
                                    font-size: 1.8rem;
                                    margin-bottom: 5px;
                                }
                            </style>

                            """, unsafe_allow_html=True)
                            # Sort the classrooms by building
                            building_classrooms = {}

                            for classroom_info in free_classes:
                                # Get the classroom name
                                classroom_name = str(classroom_info['classroom'])
                                
                                # Categorize the classroom
                                building_prefix = categorize_classroom_by_block(classroom_name)
                                
                                # Skip None values (nan or empty classrooms)
                                if building_prefix is None:
                                    continue
                                
                                # Add to appropriate category
                                if building_prefix not in building_classrooms:
                                    building_classrooms[building_prefix] = []
                                
                                building_classrooms[building_prefix].append(classroom_info)

                            # Sort buildings alphabetically (A, B, C, etc.)
                            sorted_buildings = sorted(building_classrooms.keys())

                            # Use columns container instead of markdown for layout
                            for building in sorted_buildings:
                                st.markdown(f'<div class="building-title">Block {building}</div>', unsafe_allow_html=True)
                                
                                # Calculate how many classrooms to display per row
                                classrooms_per_row = 3  # Adjust as needed
                                
                                # Sort classrooms within the same building
                                def extract_number(classroom_info):
                                    classroom_str = str(classroom_info['classroom'])
                                    digits = ''.join([c for c in classroom_str if c.isdigit()])
                                    return int(digits) if digits else 0
                                
                                sorted_classrooms = sorted(building_classrooms[building], key=extract_number)
                                
                                # Create classroom boxes using Streamlit columns
                                for i in range(0, len(sorted_classrooms), classrooms_per_row):
                                    # Create a row of columns
                                    cols = st.columns(classrooms_per_row)
                                    
                                    # Fill each column with a classroom box
                                    for col_idx, classroom_idx in enumerate(range(i, min(i + classrooms_per_row, len(sorted_classrooms)))):
                                        classroom_info = sorted_classrooms[classroom_idx]
                                        with cols[col_idx]:
                                            st.markdown(f"""
                                            <div class="classroom-box" style="width:100%; margin:0;">
                                                <div class="classroom-emoji">🏢</div>
                                                <div class="classroom-name">{classroom_info['classroom']}</div>
                                                <div class="classroom-detail">Row: {classroom_info['row']}</div>
                                            </div>
                                            """, unsafe_allow_html=True)
                                
                                # Add some spacing between buildings
                                st.markdown("<br>", unsafe_allow_html=True)
                        else:
                            
                            st.warning(f"No free {search_type} classrooms found on {selected_day} during {selected_time_slot}")    
    st.markdown("""
        <footer style="margin-top: 50px; padding: 15px; text-align: center; border-top: 1px solid #ddd; font-size: 0.9rem;">
            Academic Schedule Lookup © 2025 | 
            <a href="mailto:i232527@isb.nu.edu.pk">Report Bugs</a> | 
            <a href="https://www.linkedin.com/in/sidhart-sami-9a2051296/" target="_blank">Developer Info</a>
        </footer>
    """, unsafe_allow_html=True)


def process_cell(cell_str, search_query, my_classes_on, selected_department_code):
    if not cell_str or not is_valid_course(cell_str):
        return False
    
    # Department filter
    if selected_department_code != "All":
        dept_code = extract_department_from_course(cell_str)
        dept_matches = (
            dept_code == selected_department_code or 
            (selected_department_code.startswith("MS-") and dept_code == selected_department_code[3:]) or
            (dept_code.startswith("MS-") and selected_department_code == dept_code[3:])
        )
        if not dept_matches:
            return False
    
    # My Classes filter
    class_in_my_classes = any(my_class == cell_str.strip() for my_class in st.session_state.my_classes_list)

    # Search query filter
    search_matches = search_query.lower() in cell_str.lower() if search_query else True
    
    if my_classes_on:
        return class_in_my_classes and (not search_query or search_matches)
    else:
        return not search_query or search_matches

def create_card(cell_str, room, time, is_lab, is_my_class):
    return {
        "class": cell_str,
        "room": room,
        "time": time,
        "is_lab": is_lab,
        "is_my_class": is_my_class
    }

def namaz_break_card():
    return """
    <div style="
        border: 3px solid #FF9800;
        border-radius: 12px;
        padding: 5px;
        background-color: #FFF3E0;
        text-align: center;
        width: 100%;
        max-width: 1500px;
        margin: 20px auto;
        box-shadow: 0 4px 8px rgba(0,0,0,0.15);
    ">
        <div style="font-size: 2.5rem; margin-bottom: 10px;">🕌</div>
        <div style="font-size: 1.8rem; font-weight: bold; color: #E65100;">Namaz Break</div>
        <div style="font-size: 1.4rem; color: #BF360C; margin-top: 5px;">1:00 - 2:00 PM</div>
        <div style="font-size: 1.2rem; margin-top: 8px; color: #5D4037;">All classrooms are free during this time.</div>
    </div>
    """

def handle_empty_results(my_classes_on, search_query, selected_day, department_code):
    filter_msg = ""
    if department_code != "All":
        filter_msg = f" for {department_code} department"
    
    if my_classes_on and not search_query:
        st.warning(f"No classes found {filter_msg} on {selected_day} in your saved list")
    elif search_query:
        st.warning(f"No results found for '{search_query}'{filter_msg}")
    else:
        st.info(f"No classes found{filter_msg}. Try different filters or enable 'My Classes'")

if __name__ == "__main__":
    main()