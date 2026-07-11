import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
import io
import difflib
import os
from pyvis.network import Network
import streamlit.components.v1 as components
from supabase import create_client, Client

# ==========================================
# 🔒 PASSWORD PROTECTION (Optional - Keep if you added it!)
# ==========================================
# if "authenticated" not in st.session_state:
#     st.session_state["authenticated"] = False
# if not st.session_state["authenticated"]:
#     st.title("🎧 1Source DJ Access")
#     pwd = st.text_input("Enter Password:", type="password")
#     if st.button("Unlock App"):
#         if pwd == st.secrets["APP_PASSWORD"]:
#             st.session_state["authenticated"] = True
#             st.rerun()
#         else:
#             st.error("Incorrect password.")
#     st.stop() 

# ==========================================
# 0. SUPABASE CLOUD CONNECTION
# ==========================================
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

@st.cache_resource
def init_connection():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = init_connection()

def load_transitions():
    try:
        response = supabase.table("transitions").select("*").execute()
        if response.data:
            df = pd.DataFrame(response.data)
            df = df.rename(columns={
                "source_track": "Source Track",
                "target_track": "Target Track",
                "transition_type": "Transition Type",
                "source_note": "Source Note",
                "target_note": "Target Note"
            })
            return df
        else:
            return pd.DataFrame(columns=["id", "Source Track", "Target Track", "Transition Type", "Source Note", "Target Note", "created_at"])
    except Exception as e:
        st.error(f"Failed to connect to Supabase: {e}")
        return pd.DataFrame(columns=["id", "Source Track", "Target Track", "Transition Type", "Source Note", "Target Note", "created_at"])

st.set_page_config(page_title="Independent Rekordbox XML Editor", layout="wide")
st.title("🎵 Rekordbox XML Cue Cloner & Viewer")

# Initialize session states
if "clipboard_cues" not in st.session_state:
    st.session_state["clipboard_cues"] = None
if "clipboard_source_track" not in st.session_state:
    st.session_state["clipboard_source_track"] = ""
if "xml_tree" not in st.session_state:
    st.session_state["xml_tree"] = None
if "xml_filename" not in st.session_state:
    st.session_state["xml_filename"] = ""
if "uploaded_file_id" not in st.session_state:
    st.session_state["uploaded_file_id"] = None
if "mapping_candidates" not in st.session_state or not isinstance(st.session_state["mapping_candidates"], pd.DataFrame):
    st.session_state["mapping_candidates"] = pd.DataFrame()
if "mapping_results" not in st.session_state:
    st.session_state["mapping_results"] = ""
if "transitions_db" not in st.session_state:
    st.session_state["transitions_db"] = load_transitions()

# ==========================================
# 1. XML Database File Management
# ==========================================
st.markdown("### 📂 Load Rekordbox Collection (Optional for Transitions)")

local_xmls = [f for f in os.listdir('.') if f.endswith('.xml')]
active_index = 0
if st.session_state["xml_filename"] in local_xmls:
    active_index = local_xmls.index(st.session_state["xml_filename"]) + 1

col1, col2 = st.columns(2)
with col1:
    selected_xml = st.selectbox(
        "Select an existing XML from your folder:", 
        ["-- Choose a file --"] + local_xmls, 
        index=active_index
    )
with col2:
    uploaded_file = st.file_uploader("Or upload a new XML:", type="xml")

if uploaded_file is not None and st.session_state.get("uploaded_file_id") != uploaded_file.file_id:
    with open(uploaded_file.name, "wb") as f:
        f.write(uploaded_file.getbuffer())
    st.session_state["xml_tree"] = ET.parse(uploaded_file.name)
    st.session_state["uploaded_file_id"] = uploaded_file.file_id
    st.session_state["xml_filename"] = uploaded_file.name
    st.success(f"Successfully saved and loaded '{uploaded_file.name}'")
    st.rerun() 
elif selected_xml != "-- Choose a file --" and selected_xml != st.session_state["xml_filename"]:
    st.session_state["xml_tree"] = ET.parse(selected_xml)
    st.session_state["xml_filename"] = selected_xml
    st.rerun()

# ==========================================
# 2. Main Workspace & Data Prep
# ==========================================
df = pd.DataFrame()
tracks = []
root = None
tree = None
searchable_tracks = []

if st.session_state["xml_tree"] is not None:
    tree = st.session_state["xml_tree"]
    root = tree.getroot()
    tracks = root.findall(".//TRACK")
    
    tracks_list = []
    for track in tracks:
        tracks_list.append({
            "TrackID": track.get("TrackID", ""),
            "Artist": track.get("Artist", "Unknown"),
            "Title": track.get("Name", "Unknown"),
            "Album": track.get("Album", ""),
            "Location": track.get("Location", "")
        })
    df = pd.DataFrame(tracks_list)
    searchable_tracks = (df['Artist'] + " - " + df['Title']).tolist()
    
    st.sidebar.header("🛠️ Library Filters")
    search_query = st.sidebar.text_input("Search Artist or Title")
    if search_query:
        df = df[df['Artist'].str.contains(search_query, case=False, na=False) | 
                df['Title'].str.contains(search_query, case=False, na=False)]

    st.sidebar.markdown("---")
    st.sidebar.subheader("📋 Cue Clipboard")
    if st.session_state["clipboard_cues"]:
        st.sidebar.success(f"Loaded: {st.session_state['clipboard_source_track']}")
        st.sidebar.caption(f"Contains {len(st.session_state['clipboard_cues'])} markers")
        if st.sidebar.button("Clear Clipboard"):
            st.session_state["clipboard_cues"] = None
            st.session_state["clipboard_source_track"] = ""
            st.rerun()
    else:
        st.sidebar.info("Clipboard Empty. Copy cues from a track to get started.")

# ==========================================
# 3. Tab Layout (Always Visible)
# ==========================================
# Notice the middle tab is renamed!
tab_single, tab_data_mapping, tab_transitions = st.tabs(["📍 Single Track Editor", "🛠️ Data Mapping", "🔀 Transitions Database"])

# --- TAB 1: SINGLE TRACK ---
with tab_single:
    if st.session_state["xml_tree"] is not None:
        col1, col2 = st.columns([5, 4])
        with col1:
            st.subheader(f"Track Collection ({len(df)} tracks available)")
            selected_rows = st.dataframe(
                df, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row"
            )
            
        with col2:
            st.subheader("📍 Cue Inspection & Manipulation")
            if selected_rows and len(selected_rows["selection"]["rows"]) > 0:
                selected_index = selected_rows["selection"]["rows"][0]
                target_track_id = df.iloc[selected_index]["TrackID"]
                
                selected_track_xml = next((t for t in tracks if t.get("TrackID") == target_track_id), None)
                
                if selected_track_xml is not None:
                    track_title = selected_track_xml.get('Name')
                    track_artist = selected_track_xml.get('Artist')
                    st.markdown(f"### **{track_title}**")
                    st.caption(f"by {track_artist} | TrackID: {target_track_id}")
                    
                    position_marks = selected_track_xml.findall(".//POSITIONMARK") + selected_track_xml.findall(".//POSITION_MARK")
                    btn_col1, btn_col2 = st.columns(2)
                    
                    with btn_col1:
                        if len(position_marks) > 0:
                            if st.button("📋 Copy Cues from this Track", use_container_width=True):
                                st.session_state["clipboard_cues"] = [cue.attrib.copy() for cue in position_marks]
                                st.session_state["clipboard_source_track"] = f"{track_artist} - {track_title}"
                                st.success("Cues copied to clipboard!")
                                st.rerun()
                        else:
                            st.button("📋 Copy Cues (No cues found)", disabled=True, use_container_width=True)
                            
                    with btn_col2:
                        if st.session_state["clipboard_cues"] is not None:
                            if st.button("📥 Paste Clipboard Cues to Here", type="primary", use_container_width=True):
                                for old_mark in list(selected_track_xml.findall(".//POSITIONMARK")) + list(selected_track_xml.findall(".//POSITION_MARK")):
                                    selected_track_xml.remove(old_mark)
                                for raw_attribs in st.session_state["clipboard_cues"]:
                                    selected_track_xml.append(ET.Element("POSITION_MARK", attrib=raw_attribs))
                                st.success("Successfully cloned cues onto this track!")
                                st.rerun()
                        else:
                            st.button("📥 Paste Clipboard Cues", disabled=True, use_container_width=True)
                    st.markdown("---")

                    if position_marks:
                        cue_data = []
                        for cue in position_marks:
                            cue_type = cue.get("Type")
                            type_label = "Hot Cue" if cue_type == "0" else ("Memory Cue" if cue_type == "1" else f"Loop/Mark ({cue_type})")
                            try:
                                time_sec = float(cue.get("Start", 0.0))
                                time_str = f"{int(time_sec // 60):02d}:{time_sec % 60:05.2f}"
                            except:
                                time_str = cue.get("Start", "0.0")
                            cue_data.append({"Type": type_label, "Name": cue.get("Name", f"Cue {cue.get('Num')}"), "Timestamp": time_str, "Cue Num": cue.get("Num", "")})
                        st.table(pd.DataFrame(cue_data).sort_values(by="Cue Num"))
                    else:
                        st.info("No Hot Cues or Track Marks currently reside on this track entry.")
            else:
                st.info("👈 Select a track from the library grid to inspect cues or paste configurations.")
    else:
        st.info("📂 Please load or upload a Rekordbox XML file using the controls above to use the Single Track Editor.")

# --- TAB 2: DATA MAPPING (Nested Tabs) ---
with tab_data_mapping:
    subtab_cues, subtab_standardizer = st.tabs(["🔄 Bulk Cue Mapper", "🧹 Transitions Standardizer"])
    
    # 2A. BULK CUE MAPPER (Old Tab 2)
    with subtab_cues:
        if st.session_state["xml_tree"] is not None:
            st.subheader("Auto-Match & Bulk Copy")
            st.write("Find matching tracks (e.g., Spotify vs. Beatport) and bulk copy hot cues.")
            
            if st.button("🔍 Find Potential Matches", type="primary"):
                matches = []
                for i in range(len(df)):
                    row1 = df.iloc[i]
                    if row1['Artist'] in ["Unknown", ""]: continue
                        
                    for j in range(i + 1, len(df)):
                        row2 = df.iloc[j]
                        if row2['Artist'] in ["Unknown", ""]: continue
                            
                        if (row1['Artist'].lower() in row2['Artist'].lower()) or (row2['Artist'].lower() in row1['Artist'].lower()):
                            similarity = difflib.SequenceMatcher(None, row1['Title'].lower(), row2['Title'].lower()).ratio()
                            if similarity > 0.6:
                                n1 = root.find(f".//TRACK[@TrackID='{row1['TrackID']}']")
                                c1 = len(n1.findall(".//POSITION_MARK") + n1.findall(".//POSITIONMARK"))
                                n2 = root.find(f".//TRACK[@TrackID='{row2['TrackID']}']")
                                c2 = len(n2.findall(".//POSITION_MARK") + n2.findall(".//POSITIONMARK"))
                                
                                if c1 == 0 and c2 == 0: continue
                                action = "Copy Track 1 ➔ Track 2" if c1 > 0 and c2 == 0 else "Copy Track 2 ➔ Track 1" if c2 > 0 and c1 == 0 else "Skip (Review Required)"
                                    
                                matches.append({
                                    "Action": action,
                                    "Track 1 (Cues)": f"{row1['Title']} ({c1})", "Track 2 (Cues)": f"{row2['Title']} ({c2})",
                                    "Artist Match": f"{row1['Artist']} / {row2['Artist']}", "Similarity": f"{int(similarity * 100)}%",
                                    "ID1": row1['TrackID'], "ID2": row2['TrackID']
                                })
                if matches: st.session_state["mapping_candidates"] = pd.DataFrame(matches)
                else: st.warning("No potential matches with transferable cues found.")
            
            if len(st.session_state["mapping_candidates"]) > 0:
                edited_df = st.data_editor(
                    st.session_state["mapping_candidates"],
                    column_config={"Action": st.column_config.SelectboxColumn("Action", options=["Copy Track 1 ➔ Track 2", "Copy Track 2 ➔ Track 1", "Skip (Review Required)", "Skip"], required=True)},
                    disabled=["Track 1 (Cues)", "Track 2 (Cues)", "Artist Match", "Similarity", "ID1", "ID2"], hide_index=True, use_container_width=True
                )
                
                if st.button("🚀 Execute Bulk Copy"):
                    count = 0
                    for _, row in edited_df.iterrows():
                        if "Skip" in row["Action"]: continue
                        s_id, t_id = (row['ID1'], row['ID2']) if row["Action"] == "Copy Track 1 ➔ Track 2" else (row['ID2'], row['ID1'])
                        s_node, t_node = root.find(f".//TRACK[@TrackID='{s_id}']"), root.find(f".//TRACK[@TrackID='{t_id}']")
                        
                        if s_node is not None and t_node is not None:
                            for old in list(t_node.findall(".//POSITIONMARK")) + list(t_node.findall(".//POSITION_MARK")): t_node.remove(old)
                            for cue in s_node.findall(".//POSITIONMARK") + s_node.findall(".//POSITION_MARK"): t_node.append(ET.Element("POSITION_MARK", attrib=cue.attrib.copy()))
                            count += 1
                                
                    st.session_state["mapping_results"] = f"Executed cue copying on {count} pairs!"
                    st.session_state["mapping_candidates"] = pd.DataFrame() 
                    st.rerun()

            if st.session_state.get("mapping_results"):
                st.success(st.session_state["mapping_results"])
                st.session_state["mapping_results"] = ""
        else:
            st.info("📂 Please load a Rekordbox XML file to use the Bulk Mapper.")

    # 2B. DATABASE STANDARDIZER (The New Feature!)
    with subtab_standardizer:
        st.subheader("🧹 Database Standardizer")
        st.write("Cross-reference your cloud transitions database against your Rekordbox XML to fix misspellings and link disconnected tracks.")
        
        if st.session_state["xml_tree"] is not None and len(st.session_state["transitions_db"]) > 0:
            if st.button("🔎 Scan Database for Unverified Tracks", type="primary"):
                db_tracks = pd.concat([st.session_state["transitions_db"]["Source Track"], st.session_state["transitions_db"]["Target Track"]]).dropna().unique()
                
                standardization_candidates = []
                for track in db_tracks:
                    if track not in searchable_tracks:
                        # Find the closest match in the XML
                        best_matches = difflib.get_close_matches(str(track), searchable_tracks, n=1, cutoff=0.3)
                        suggestion = best_matches[0] if best_matches else "No obvious match found"
                        default_action = "Update to Rekordbox Name" if best_matches else "Ignore"
                        
                        standardization_candidates.append({
                            "Action": default_action,
                            "Original DB Name (⚠️)": track,
                            "Suggested Rekordbox Name (✅)": suggestion
                        })
                
                if standardization_candidates:
                    st.session_state["std_candidates"] = pd.DataFrame(standardization_candidates)
                else:
                    st.success("🎉 All tracks in your database perfectly match your Rekordbox XML!")
                    st.session_state["std_candidates"] = pd.DataFrame()

            if "std_candidates" in st.session_state and not st.session_state["std_candidates"].empty:
                st.markdown("### Review & Fix Tracks")
                std_df = st.data_editor(
                    st.session_state["std_candidates"],
                    column_config={
                        "Action": st.column_config.SelectboxColumn("Action", options=["Update to Rekordbox Name", "Ignore"], required=True)
                    },
                    disabled=["Original DB Name (⚠️)", "Suggested Rekordbox Name (✅)"], hide_index=True, use_container_width=True
                )
                
                if st.button("🚀 Push Fixes to Cloud Database"):
                    updates_made = 0
                    for _, row in std_df.iterrows():
                        if row["Action"] == "Update to Rekordbox Name" and row["Suggested Rekordbox Name (✅)"] != "No obvious match found":
                            old_name = row["Original DB Name (⚠️)"]
                            new_name = row["Suggested Rekordbox Name (✅)"]
                            
                            # Update all Source instances
                            supabase.table("transitions").update({"source_track": new_name}).eq("source_track", old_name).execute()
                            # Update all Target instances
                            supabase.table("transitions").update({"target_track": new_name}).eq("target_track", old_name).execute()
                            updates_made += 1
                            
                    st.success(f"Successfully standardized {updates_made} track names in the cloud!")
                    st.session_state["transitions_db"] = load_transitions() # Reload clean data
                    st.session_state["std_candidates"] = pd.DataFrame() # Clear table
                    st.rerun()
        else:
            st.info("📂 Please ensure an XML is loaded and your database has transitions to scan.")


# --- TAB 3: TRANSITIONS ---
with tab_transitions:
    st.subheader("🔀 Transitions Database")
    st.subheader("➕ Add New Transition")
    
    t_col1, t_col2 = st.columns(2)
    with t_col1:
        if not df.empty:
            source_track = st.selectbox("🎵 Source Track (Playing):", options=searchable_tracks, index=None, placeholder="Search library...")
        else:
            source_track = st.text_input("🎵 Source Track (Playing):", placeholder="e.g., Artist - Title")
            
    with t_col2:
        if not df.empty:
            target_track = st.selectbox("🎵 Target Track (Mixing Into):", options=searchable_tracks, index=None, placeholder="Search library...")
        else:
            target_track = st.text_input("🎵 Target Track (Mixing Into):", placeholder="e.g., Artist - Title")
            
    trans_type = st.selectbox("🎛️ Transition Type", ["BPM Transition", "Wordplay / Tone Play", "Drop Swap", "Mashup / Blend", "Loop & Filter", "Other"])
    
    note_col1, note_col2 = st.columns(2)
    with note_col1:
        source_note = st.text_input("📝 Source Note (Exit Strategy)", placeholder="e.g., Loop 16 beats at vocal")
    with note_col2:
        target_note = st.text_input("📝 Target Note (Entry Strategy)", placeholder="e.g., Drop on the 1 with low filter")
    
    if st.button("☁️ Log Transition to Cloud", type="primary"):
        if source_track and target_track:
            try:
                supabase.table("transitions").insert({
                    "source_track": source_track, "target_track": target_track,
                    "transition_type": trans_type, "source_note": source_note, "target_note": target_note
                }).execute()
                st.success("Transition synced to the cloud!")
                st.session_state["transitions_db"] = load_transitions()
                st.rerun()
            except Exception as e:
                st.error(f"Error saving to cloud: {e}")
        else:
            st.warning("Please provide both a Source and Target track.")
            
    st.markdown("---")
    st.subheader("👀 View Transitions")
    tab_table, tab_graph = st.tabs(["📋 Data Table", "🕸️ Visual Web Map"])
    
    with tab_table:
        if len(st.session_state["transitions_db"]) > 0:
            # Build the display dataframe with ✅ and ⚠️
            display_df = st.session_state["transitions_db"].copy()
            if not df.empty:
                valid_set = set(searchable_tracks)
                display_df["Source Track"] = display_df["Source Track"].apply(lambda x: f"✅ {x}" if x in valid_set else f"⚠️ {x}")
                display_df["Target Track"] = display_df["Target Track"].apply(lambda x: f"✅ {x}" if x in valid_set else f"⚠️ {x}")
            
            st.dataframe(display_df, use_container_width=True, hide_index=True)
        else:
            st.info("No transitions logged yet. Add one above to populate your cloud database.")

    with tab_graph:
        if len(st.session_state["transitions_db"]) > 0:
            net = Network(height='500px', width='100%', bgcolor='#0E1117', font_color='white', directed=True)
            added_nodes = set()
            
            for index, row in st.session_state["transitions_db"].iterrows():
                source, target, t_type = str(row["Source Track"]), str(row["Target Track"]), row["Transition Type"]
                if pd.isna(source) or pd.isna(target) or source == "nan" or target == "nan": continue
                
                # Color code: If XML is loaded, color verified tracks differently than unverified ones in the graph!
                s_color = '#45B7D1' if (df.empty or source in searchable_tracks) else '#FFA500'
                t_color = '#FF6B6B' if (df.empty or target in searchable_tracks) else '#FFA500'

                if source not in added_nodes:
                    net.add_node(source, label=source, title=f"Track: {source}", color=s_color)
                    added_nodes.add(source)
                if target not in added_nodes:
                    net.add_node(target, label=target, title=f"Track: {target}", color=t_color)
                    added_nodes.add(target)
                net.add_edge(source, target, title=f"Type: {t_type}", label=t_type, color="#888888")
                
            net.repulsion(node_distance=150, spring_length=200)
            try:
                os.makedirs('html_files', exist_ok=True)
                net.save_graph('html_files/pyvis_graph.html')
                components.html(open('html_files/pyvis_graph.html', 'r', encoding='utf-8').read(), height=515)
            except Exception as e:
                st.warning(f"Could not render visualizer: {e}")
        else:
            st.info("Add some transitions above to generate your web map!")

    st.markdown("---")
    col_imp, col_save, col_exp = st.columns(3)
    with col_imp:
        st.markdown("**🔄 Refresh Data**")
        if st.button("☁️ Sync from Cloud", use_container_width=True):
            st.session_state["transitions_db"] = load_transitions()
            st.success("Database synced successfully!")
            st.rerun()
    with col_exp:
        st.markdown("**📤 Download Copy**")
        if len(st.session_state["transitions_db"]) > 0:
            st.download_button(label="🚀 Download Backup (CSV)", data=st.session_state["transitions_db"].to_csv(index=False).encode('utf-8'), file_name="my_dj_transitions_backup.csv", mime="text/csv", use_container_width=True)
        else:
            st.button("🚀 Download Backup (CSV)", disabled=True, use_container_width=True)

# ==========================================
# 4. XML Export Sidebar
# ==========================================
if st.session_state["xml_tree"] is not None:
    st.sidebar.markdown("---")
    st.sidebar.subheader("💾 Export Modifications")
    buffer = io.BytesIO()
    buffer.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
    tree.write(buffer, encoding="utf-8", xml_declaration=False)
    st.sidebar.download_button(label="🚀 Download Modified XML", data=buffer.getvalue(), file_name="rekordbox_updated_collection.xml", mime="application/xml", use_container_width=True)
