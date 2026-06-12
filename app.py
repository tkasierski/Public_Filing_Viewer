import requests
import pandas as pd
import streamlit as st

# Configure the dashboard browser tab
st.set_page_config(page_title="Custom Calcbench Engine", layout="wide")

st.title("📊 Multi-Year XBRL Discovery Engine")
st.caption("A cloud-native portal to analyze raw, non-normalized SEC disclosure data in browser memory.")

# 1. User Inputs
headers = {'User-Agent': "PortfolioManager research@firm.com"}
ticker = st.sidebar.text_input("Enter Company Ticker:", value="TSLA").upper()

@st.cache_data(ttl=3600)
def fetch_company_xbrl_index(ticker_str):
    """Fetches the complete XBRL fact dictionary map for a single company."""
    try:
        # Get CIK
        ticker_map = requests.get("https://sec.gov/files/company_tickers.json", headers=headers).json()
        cik = next((str(item['cik_str']).zfill(10) for item in ticker_map.values() if item['ticker'] == ticker_str), None)
        
        if not cik:
            return None, "Ticker not found."
            
        # Pull complete facts profile (JSON)
        facts_url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
        res = requests.get(facts_url, headers=headers)
        return res.json(), None
    except Exception as e:
        return None, str(e)

# 2. Process Company Profile
if ticker:
    raw_data, error = fetch_company_xbrl_index(ticker)
    
    if error:
        st.error(f"Error loading data: {error}")
    elif raw_data:
        # Extract namespaces (e.g., 'us-gaap', 'tsla' custom extensions)
        namespaces = list(raw_data['facts'].keys())
        
        # Build a searchable master directory of ALL available tags for this specific company
        available_metrics = []
        for ns in namespaces:
            for tag, meta in raw_data['facts'][ns].items():
                available_metrics.append({
                    "Namespace": ns,
                    "XBRL Tag": tag,
                    "Label/Description": meta.get('label', 'No label provided')
                })
        
        df_menu = pd.DataFrame(available_metrics)
        
        # Sidebar UI controls for discovery
        st.sidebar.markdown("### 🔍 Taxonomy Discovery")
        selected_ns = st.sidebar.selectbox("Filter Framework:", ["All"] + namespaces)
        
        filtered_menu = df_menu if selected_ns == "All" else df_menu[df_menu['Namespace'] == selected_ns]
        
        # Search box to find specific items like 'Delivery', 'Revenue', or 'Geographic'
        search_query = st.sidebar.text_input("Search metrics (e.g., 'delivery' or 'segment'):", "")
        if search_query:
            filtered_menu = filtered_menu[
                filtered_menu['XBRL Tag'].str.contains(search_query, case=False) | 
                filtered_menu['Label/Description'].str.contains(search_query, case=False)
            ]
            
        st.sidebar.write(f"Found {len(filtered_menu)} viewable disclosure tracks.")
        
        # 3. Metric Selection Dropdown populated dynamically
        metric_labels = filtered_menu['Label/Description'] + " [" + filtered_menu['XBRL Tag'] + "]"
        selected_metric_label = st.selectbox("Select a metric to isolate historical trend:", metric_labels)
        
        if selected_metric_label:
            # Extract target tag back out of label string
            target_tag = selected_metric_label.split("[")[-1].split("]")[0]
            target_ns = filtered_menu[filtered_menu['XBRL Tag'] == target_tag]['Namespace'].values[0]
            
            # Extract historical entries for chosen item
            units_dict = raw_data['facts'][target_ns][target_tag]['units']
            unit_key = list(units_dict.keys())[0]  # Grab units automatically (USD, shares, pure, vehicles)
            
            raw_history = units_dict[unit_key]
            df_history = pd.DataFrame(raw_history)
            
            # 4. Multi-Form Visibility Configuration
            st.markdown("### 📋 Filter Disclosure Sources")
            available_forms = df_history['form'].unique().tolist()

            # FIX: This dynamically picks defaults only if they actually exist in the data
            default_forms = [f for f in ["10-K", "10-Q", "8-K"] if f in available_forms]
            if not default_forms and available_forms:
                default_forms = [available_forms[0]] # Fallback to first available if none match

            selected_forms = st.multiselect("Select filing variants to include:", available_forms, default=default_forms)

            # Clean and isolate data based on selections
            df_filtered = df_history[df_history['form'].isin(selected_forms)].copy()
            
            # Handle Dimensional Breakdowns (Segment reporting / Segment axes)
            if 'segment' in df_filtered.columns:
                # Fill missing segments with 'Consolidated' line items
                df_filtered['segment'] = df_filtered['segment'].fillna('Consolidated / Corporate')
            else:
                df_filtered['segment'] = 'Consolidated / Corporate'
                
            # Clean up timeline sorting
            df_filtered = df_filtered.sort_values(by=['fy', 'fp', 'filed'])
            
            # 5. Render Normalized Comparative Grid
            st.markdown(f"## Data Overview: `{target_tag}`")
            
            # Reorganize the grid for instant scanning without clicking
            display_grid = df_filtered[['fy', 'fp', 'form', 'filed', 'val', 'segment']].rename(
                columns={'fy': 'Fiscal Year', 'fp': 'Period', 'form': 'Filing Type', 'filed': 'Date Filed', 'val': f'Value ({unit_key})', 'segment': 'Segment/Dimension'}
            )
            
            # Display interactive spreadsheet grid in browser memory
            st.dataframe(display_grid, use_container_width=True, hide_index=True)
            
            # Graph trends for segmented and unified metrics
            if len(display_grid) > 0:
                st.markdown("### 📈 Visual Trend Matrix")
                st.line_chart(data=display_grid, x="Date Filed", y=f"Value ({unit_key})", color="Segment/Dimension")
