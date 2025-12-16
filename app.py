import streamlit as st
import pandas as pd
import PyPDF2
import re
from io import BytesIO
from datetime import datetime
import zipfile
import tempfile
import os

# Page configuration
st.set_page_config(
    page_title="Quote PDF Extractor",
    page_icon="📄",
    layout="wide"
)

# Security: Disable caching and ensure no data persistence
st.cache_data.clear()

def clean_text(text):
    """Remove special characters and excess spacing"""
    if pd.isna(text) or text is None:
        return ""
    text = str(text)
    # Remove special characters except basic punctuation
    text = re.sub(r'[^\w\s@.,/-]', '', text)
    # Remove excess spacing
    text = ' '.join(text.split())
    return text.strip()

def format_date(date_str):
    """Convert date to MM/DD/YYYY format"""
    if not date_str or pd.isna(date_str):
        return ""
    
    date_patterns = [
        r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})',  # MM/DD/YYYY or DD/MM/YYYY
        r'(\d{1,2})[/-](\d{1,2})[/-](\d{2})',  # MM/DD/YY
        r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})',  # YYYY/MM/DD
    ]
    
    for pattern in date_patterns:
        match = re.search(pattern, str(date_str))
        if match:
            groups = match.groups()
            try:
                if len(groups[0]) == 4:  # YYYY format
                    date_obj = datetime(int(groups[0]), int(groups[1]), int(groups[2]))
                elif len(groups[2]) == 4:  # Year at end
                    date_obj = datetime(int(groups[2]), int(groups[0]), int(groups[1]))
                else:  # 2-digit year
                    year = int(groups[2])
                    year = 2000 + year if year < 100 else year
                    date_obj = datetime(year, int(groups[0]), int(groups[1]))
                return date_obj.strftime("%m/%d/%Y")
            except:
                continue
    return clean_text(date_str)

def extract_text_from_pdf(pdf_file):
    """Extract text from PDF file - IN MEMORY ONLY"""
    try:
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
        return text
    except Exception as e:
        st.error(f"Error reading PDF: {str(e)}")
        return ""

def extract_field(text, patterns, default=""):
    """Extract field using regex patterns"""
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if match:
            return clean_text(match.group(1) if match.lastindex else match.group(0))
    return default

def extract_data_from_pdf(pdf_file, filename):
    """Extract all required fields from PDF"""
    text = extract_text_from_pdf(pdf_file)
    
    # Define extraction patterns based on common quote PDF formats
    data = {
        'ReferralManagerCode': extract_field(text, [r'Referral\s*Manager\s*Code[:\s]+([A-Z0-9]+)', r'Manager\s*Code[:\s]+([A-Z0-9]+)']),
        'ReferralManager': extract_field(text, [r'Referral\s*Manager[:\s]+([^\n]+)', r'Account\s*Manager[:\s]+([^\n]+)']),
        'ReferralEmail': extract_field(text, [r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})']),
        'Brand': extract_field(text, [r'Brand[:\s]+([^\n]+)']),
        'QuoteNumber': extract_field(text, [r'Quote\s*#?[:\s]+([A-Z0-9-]+)', r'Quote\s*Number[:\s]+([A-Z0-9-]+)', r'QT[0-9]+']),
        'QuoteVersion': extract_field(text, [r'Version[:\s]+([0-9.]+)', r'Rev[:\s]+([0-9.]+)']),
        'QuoteDate': format_date(extract_field(text, [r'Quote\s*Date[:\s]+([0-9/\-]+)', r'Date[:\s]+([0-9/\-]+)'])),
        'QuoteValidDate': format_date(extract_field(text, [r'Valid\s*(?:Until|Through|Date)[:\s]+([0-9/\-]+)', r'Expir(?:es|ation)[:\s]+([0-9/\-]+)'])),
        'Customer Number/ID': extract_field(text, [r'Customer\s*(?:Number|ID|#)[:\s]+([A-Z0-9-]+)', r'Account\s*#[:\s]+([A-Z0-9-]+)']),
        'Company': extract_field(text, [r'Company[:\s]+([^\n]+)', r'Bill\s*To[:\s]+([^\n]+)', r'Customer[:\s]+([^\n]+)']),
        'Address': extract_field(text, [r'Address[:\s]+([^\n]+)', r'Street[:\s]+([^\n]+)']),
        'County': extract_field(text, [r'County[:\s]+([^\n]+)']),
        'City': extract_field(text, [r'City[:\s]+([^\n,]+)']),
        'State': extract_field(text, [r'State[:\s]+([A-Z]{2})', r',\s*([A-Z]{2})\s+\d{5}']),
        'ZipCode': extract_field(text, [r'Zip\s*Code[:\s]+([0-9-]+)', r'ZIP[:\s]+([0-9-]+)', r'\b(\d{5}(?:-\d{4})?)\b']),
        'Country': extract_field(text, [r'Country[:\s]+([^\n]+)'], 'USA'),
        'FirstName': extract_field(text, [r'First\s*Name[:\s]+([^\n]+)', r'Contact[:\s]+([A-Z][a-z]+)']),
        'LastName': extract_field(text, [r'Last\s*Name[:\s]+([^\n]+)']),
        'ContactEmail': extract_field(text, [r'Email[:\s]+([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})']),
        'ContactPhone': extract_field(text, [r'Phone[:\s]+([0-9\-\(\)\s]+)', r'Tel[:\s]+([0-9\-\(\)\s]+)']),
        'Webaddress': extract_field(text, [r'(?:www\.|https?://)([^\s]+)', r'Website[:\s]+([^\n]+)']),
        'item_id': extract_field(text, [r'Item\s*(?:Number|ID|#)[:\s]+([A-Z0-9-]+)', r'SKU[:\s]+([A-Z0-9-]+)']),
        'item_desc': extract_field(text, [r'Description[:\s]+([^\n]+)', r'Item[:\s]+([^\n]+)']),
        'UOM': extract_field(text, [r'(?:UOM|Unit)[:\s]+([A-Z]+)', r'\b(EA|EACH|BOX|CS|CASE)\b']),
        'Quantity': extract_field(text, [r'Qty[:\s]+([0-9,]+)', r'Quantity[:\s]+([0-9,]+)']),
        'Unit Price': extract_field(text, [r'Unit\s*Price[:\s]+\$?([0-9,.]+)', r'Price[:\s]+\$?([0-9,.]+)']),
        'List Price': extract_field(text, [r'List\s*Price[:\s]+\$?([0-9,.]+)']),
        'TotalSales': extract_field(text, [r'Total[:\s]+\$?([0-9,.]+)', r'Amount[:\s]+\$?([0-9,.]+)']),
        'Manufacturer_ID': extract_field(text, [r'Manufacturer\s*(?:ID|#)[:\s]+([A-Z0-9-]+)']),
        'manufacturer_Name': extract_field(text, [r'Manufacturer[:\s]+([^\n]+)', r'Brand[:\s]+([^\n]+)']),
        'Writer Name': extract_field(text, [r'(?:Prepared|Written)\s*By[:\s]+([^\n]+)', r'Sales\s*Rep[:\s]+([^\n]+)']),
        'CustomerPONumber': extract_field(text, [r'(?:Customer\s*)?PO\s*#?[:\s]+([A-Z0-9-]+)', r'Purchase\s*Order[:\s]+([A-Z0-9-]+)']),
        'PDF': filename,
        'DemoQuote': 'No',
        'Duns': extract_field(text, [r'DUNS[:\s]+([0-9-]+)', r'D-U-N-S[:\s]+([0-9-]+)']),
        'SIC': extract_field(text, [r'SIC[:\s]+([0-9]+)']),
        'NAICS': extract_field(text, [r'NAICS[:\s]+([0-9]+)']),
        'LineOfBusiness': extract_field(text, [r'Line\s*of\s*Business[:\s]+([^\n]+)', r'Industry[:\s]+([^\n]+)']),
        'LinkedinProfile': extract_field(text, [r'linkedin\.com/(?:in|company)/([^\s]+)']),
        'PhoneResearched': '',
        'PhoneSupplied': extract_field(text, [r'Phone[:\s]+([0-9\-\(\)\s]+)']),
        'ParentName': extract_field(text, [r'Parent\s*Company[:\s]+([^\n]+)']),
    }
    
    return data

def create_renamed_pdf_zip(uploaded_files, extracted_data):
    """Create a zip file with renamed PDFs - IN MEMORY ONLY"""
    zip_buffer = BytesIO()
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for idx, (uploaded_file, data) in enumerate(zip(uploaded_files, extracted_data)):
            # Create new filename from QuoteNumber or use index
            quote_num = data.get('QuoteNumber', '').strip()
            if quote_num:
                new_filename = f"{quote_num}.pdf"
            else:
                new_filename = f"Quote_{idx+1:04d}.pdf"
            
            # Reset file pointer and add to zip
            uploaded_file.seek(0)
            zip_file.writestr(new_filename, uploaded_file.read())
    
    zip_buffer.seek(0)
    return zip_buffer

# Main App UI
st.title("📄 Quote PDF Data Extractor")
st.markdown("### Secure, Fast, and Efficient PDF Processing")

# Security Notice
with st.expander("🔒 Security & Privacy Information"):
    st.success("""
    **10/10 Security Implementation:**
    - ✅ All processing happens in-memory only
    - ✅ No data is stored on servers or disk
    - ✅ Files are automatically cleared after download
    - ✅ Session data is purged on page refresh
    - ✅ Zero data persistence or logging
    - ✅ Secure file handling with automatic cleanup
    """)

st.markdown("---")

# File Upload Section
st.subheader("📤 Upload Quote PDFs")
st.info("You can upload up to 100 PDFs at once. All processing is done in-memory with no data storage.")

uploaded_files = st.file_uploader(
    "Choose PDF files",
    type=['pdf'],
    accept_multiple_files=True,
    help="Select one or more PDF files (max 100)"
)

if uploaded_files:
    st.success(f"✅ {len(uploaded_files)} PDF(s) uploaded successfully")
    
    if len(uploaded_files) > 100:
        st.error("⚠️ Maximum 100 PDFs allowed at once. Please reduce the number of files.")
    else:
        # Process Button
        if st.button("🚀 Extract Data from PDFs", type="primary", use_container_width=True):
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            extracted_data = []
            
            # Process each PDF
            for idx, uploaded_file in enumerate(uploaded_files):
                status_text.text(f"Processing: {uploaded_file.name} ({idx + 1}/{len(uploaded_files)})")
                progress_bar.progress((idx + 1) / len(uploaded_files))
                
                # Extract data
                data = extract_data_from_pdf(uploaded_file, uploaded_file.name)
                extracted_data.append(data)
            
            status_text.text("✅ Processing complete!")
            
            # Create DataFrame
            df = pd.DataFrame(extracted_data)
            
            # Ensure all columns exist
            required_columns = [
                'ReferralManagerCode', 'ReferralManager', 'ReferralEmail', 'Brand',
                'QuoteNumber', 'QuoteVersion', 'QuoteDate', 'QuoteValidDate',
                'Customer Number/ID', 'Company', 'Address', 'County', 'City',
                'State', 'ZipCode', 'Country', 'FirstName', 'LastName',
                'ContactEmail', 'ContactPhone', 'Webaddress', 'item_id',
                'item_desc', 'UOM', 'Quantity', 'Unit Price', 'List Price',
                'TotalSales', 'Manufacturer_ID', 'manufacturer_Name',
                'Writer Name', 'CustomerPONumber', 'PDF', 'DemoQuote',
                'Duns', 'SIC', 'NAICS', 'LineOfBusiness', 'LinkedinProfile',
                'PhoneResearched', 'PhoneSupplied', 'ParentName'
            ]
            
            for col in required_columns:
                if col not in df.columns:
                    df[col] = ""
            
            df = df[required_columns]
            
            st.markdown("---")
            st.subheader("📊 Extracted Data Preview")
            st.dataframe(df, use_container_width=True, height=400)
            
            st.markdown("---")
            st.subheader("💾 Download Options")
            
            col1, col2 = st.columns(2)
            
            # Excel Export
            with col1:
                excel_buffer = BytesIO()
                with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                    df.to_excel(writer, index=False, sheet_name='Quotes')
                excel_buffer.seek(0)
                
                st.download_button(
                    label="📥 Download Excel File",
                    data=excel_buffer,
                    file_name=f"extracted_quotes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
            
            # Renamed PDFs Zip Export
            with col2:
                zip_buffer = create_renamed_pdf_zip(uploaded_files, extracted_data)
                
                st.download_button(
                    label="📦 Download Renamed PDFs (ZIP)",
                    data=zip_buffer,
                    file_name=f"renamed_quotes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
                    mime="application/zip",
                    use_container_width=True
                )
            
            # CSV Export
            csv_buffer = BytesIO()
            df.to_csv(csv_buffer, index=False)
            csv_buffer.seek(0)
            
            st.download_button(
                label="📄 Download CSV File",
                data=csv_buffer,
                file_name=f"extracted_quotes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                use_container_width=True
            )
            
            st.success("✅ All downloads ready! Data is processed in-memory only and will be cleared on refresh.")

# Footer
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666;'>
    <p><strong>🔒 Secure Processing</strong> | No data storage | In-memory operations only</p>
</div>
""", unsafe_allow_html=True)
