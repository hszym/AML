
import pandas as pd
import streamlit as st
import os
import urllib.parse
from datetime import datetime

st.set_page_config(layout="wide", page_title="AML Monaco Portal")

# --- 1. CONFIGURATION ---
dev_mode = st.sidebar.toggle("🛠️ Dev Mode", value=False)
BASE_DIR = (
    r"C:\Users\Hugo Szym\OneDrive - Plurimi\Automation_Project\Transactions Monitoring"
    if dev_mode else
    r"C:\Users\ChiaraIncardona\OneDrive - Plurimi\Documents - Plurimi Wealth (Monaco) SAM\Compliance\PROCEDURES\MCO AML TR MONITORING\MONTHLY MONITORING\2026"
)
RM_EMAIL_FILE = os.path.join(BASE_DIR, "RM_Emails.xlsx")
ETHR_FILE = os.path.join(BASE_DIR, "ETHR_List.xlsx")
COMPLIANCE_PASSWORD = "Chiara"

# --- HELPER: Detect the portfolio number column name ---
def get_portf_num_col(df):
    """Returns the portfolio number column name found in the dataframe, or None."""
    candidates = ['Portf. No', 'Portf No', 'Portfolio No', 'Portfolio Number',
                  'Portfolio_No', 'PortfolioNo', 'Portf. Number', 'Portfolio_Number', 'Portf_No']
    for c in candidates:
        if c in df.columns:
            return c
    return None

# --- 2. AML RULES ENGINE ---
def apply_aml_rules(df):
    # Chargement de la liste ETHR
    ethr_countries = []
    if os.path.exists(ETHR_FILE):
        try:
            ethr_df = pd.read_excel(ETHR_FILE)
            if 'Country' in ethr_df.columns:
                ethr_countries = ethr_df['Country'].astype(str).str.strip().unique().tolist()
        except Exception as e:
            st.error(f"Erreur lors de la lecture du fichier ETHR: {e}")

    flags = []

    for _, row in df.iterrows():
        reasons = []

        # --- NETTOYAGE ROBUSTE DES MONTANTS ---
        def clean_val(val):
            if pd.isna(val): return 0.0
            s_val = str(val).replace(',', '').strip()
            try:
                return float(s_val)
            except ValueError:
                return 0.0

        amt = clean_val(row.get('Amount', 0))
        abs_amt = abs(amt)
        cum_amt = clean_val(row.get('Cumulated Amount per Mandate', 0))
        abs_cum_amt = abs(cum_amt)

        score = str(row.get('AML_Risk_Score', '')).strip().capitalize()
        country = str(row.get('Residence Country', '')).strip()
        desc = str(row.get('Tr. description', row.get('Tr description', row.get('Description', '')))).upper()

        # RÈGLE 1: Risque vs Montant Individuel
        if score == 'High' and abs_amt >= 50000:
            reasons.append(f"High Risk > 50k ({abs_amt:,.2f})")
        elif score == 'Medium' and abs_amt >= 75000:
            reasons.append(f"Med Risk > 75k ({abs_amt:,.2f})")
        elif score == 'Low' and abs_amt >= 100000:
            reasons.append(f"Low Risk > 100k ({abs_amt:,.2f})")

        # RÈGLE 2: Risque vs Montant Cumulé
        if score == 'High' and abs_cum_amt >= 200000:
            reasons.append("High Risk Abs Cumul > 200k")
        elif score == 'Medium' and abs_cum_amt >= 300000:
            reasons.append("Med Risk Abs Cumul > 300k")
        elif score == 'Low' and abs_cum_amt >= 400000:
            reasons.append("Low Risk Abs Cumul > 400k")

        # RÈGLE 3: Pays ETHR
        if country in ethr_countries and abs_amt >= 10000:
            reasons.append(f"ETHR Country ({country}) > 10k")

        # RÈGLE 4: Retraits d'espèces
        if amt <= -30000 and any(w in desc for w in ["RETRAIT", "DAB", "ESPECES"]):
            reasons.append("Withdrawal > 30k (DAB/Specie)")

        flags.append("; ".join(reasons) if reasons else "Clear")

    df['AML_Flag_Reason'] = flags
    return df

# --- 3. FILE HELPERS ---
def get_month_folder(month_str):
    return os.path.join(BASE_DIR, f"Monaco_{month_str}")

def get_docs_folder(month_str):
    path = os.path.join(get_month_folder(month_str), "Supporting_Docs")
    if not os.path.exists(path): os.makedirs(path)
    return path

def get_rm_email(rm_name):
    if os.path.exists(RM_EMAIL_FILE):
        emails_df = pd.read_excel(RM_EMAIL_FILE)
        match = emails_df[emails_df['Portf. Manager'] == rm_name]
        return match.iloc[0]['Email'] if not match.empty else ""
    return ""

def initialize_files(uploaded_file, month_str):
    folder_path = get_month_folder(month_str)
    if not os.path.exists(folder_path): os.makedirs(folder_path)
    get_docs_folder(month_str)

    df = pd.read_excel(uploaded_file)

    # Rename description column to standard name
    possible_desc_names = ['Tr. description', 'Tr description', 'Description', 'Transaction Description']
    for name in possible_desc_names:
        if name in df.columns:
            df = df.rename(columns={name: 'Tr. description'})
            break

    df.to_excel(os.path.join(folder_path, f"AML Cashflows - Monaco - {month_str} - Expersoft.xlsx"), index=False)

    df['Ref'] = [f"TRX-{1000+i}" for i in range(len(df))]
    for col in ['Date to RM', 'Date of Response', 'Date Resolved', 'Resolved', 'Explanation', 'Compliance_Comments', 'Doc_Path']:
        df[col] = ""
    df['Resolved'] = "No"
    df = apply_aml_rules(df)

    path = os.path.join(folder_path, f"AML Cashflows - Monaco - {month_str} - Reviewed.xlsx")
    df.to_excel(path, index=False)
    return path

# --- 4. NAVIGATION ---
role = st.sidebar.radio("Navigation", ["Banker Portal", "Compliance Dashboard"])

# ============================================================
# BANKER PORTAL
# ============================================================
if role == "Banker Portal":
    st.title("🏦 Banker Justification Portal")
    folders = sorted([f for f in os.listdir(BASE_DIR) if f.startswith("Monaco_")], reverse=True)

    if folders:
        sel_m = st.selectbox("Select Month to Justify", folders)
        m_val = sel_m.split('_')[1]
        b_path = os.path.join(BASE_DIR, sel_m, f"AML Cashflows - Monaco - {m_val} - Reviewed.xlsx")
        b_data = pd.read_excel(b_path).fillna("")
        b_data['Tr. date'] = pd.to_datetime(b_data['Tr. date'], errors='coerce').dt.strftime('%d %b %Y').fillna("")

        portf_num_col = get_portf_num_col(b_data)

        rm_list = sorted(b_data['Portf. Manager'].unique())
        my_name = st.selectbox("Select Your Name", rm_list)

        # Reset checked/expanded state when banker or month changes
        state_ctx = f"{sel_m}_{my_name}"
        if st.session_state.get('_bp_ctx') != state_ctx:
            for k in list(st.session_state.keys()):
                if k.startswith(('chk_', 'exp_', 'ans_', 'batch_')):
                    del st.session_state[k]
            st.session_state['_bp_ctx'] = state_ctx

        tasks = b_data[
            (b_data['Portf. Manager'] == my_name) &
            (b_data['Date to RM'] != "") &
            (b_data['Resolved'] == "No")
        ].copy()

        if not tasks.empty:
            # Refs currently checked
            checked = [ref for ref in tasks['Ref'] if st.session_state.get(f"chk_{ref}", False)]

            # ── BATCH SECTION — appears at top only when ≥1 card is checked ──
            if checked:
                with st.container(border=True):
                    st.markdown(f"**📋 Batch justify {len(checked)} transaction(s):** {', '.join(checked)}")
                    batch_ans = st.text_area(
                        "Shared Explanation",
                        key="batch_ans",
                        placeholder="Enter the explanation to apply to all selected transactions..."
                    )
                    if st.button("✅ Submit for Selected", type="primary", key="batch_submit"):
                        if batch_ans:
                            for ref in checked:
                                match = tasks[tasks['Ref'] == ref]
                                if not match.empty:
                                    i = match.index[0]
                                    b_data.at[i, 'Explanation'] = batch_ans
                                    b_data.at[i, 'Resolved'] = "Waiting for Compliance"
                                    b_data.at[i, 'Date of Response'] = datetime.now().strftime("%Y-%m-%d")
                                    st.session_state[f"chk_{ref}"] = False
                            b_data.to_excel(b_path, index=False)
                            st.success(f"Submitted {len(checked)} transaction(s).")
                            st.rerun()
                        else:
                            st.error("Please enter a justification before submitting.")

            # ── TRANSACTION CARDS ──
            for idx, row in tasks.iterrows():
                ref = row['Ref']
                is_expanded = st.session_state.get(f"exp_{ref}", False)
                has_rejection = bool(str(row.get('Compliance_Comments', '')).strip())

                with st.container(border=True):
                    # Collapsed header: checkbox | transaction info | expand button
                    col_chk, col_info, col_btn = st.columns([0.3, 10, 0.9])

                    col_chk.checkbox("", key=f"chk_{ref}", label_visibility="collapsed")

                    portf_no_part = f" &nbsp;·&nbsp; `{row[portf_num_col]}`" if portf_num_col else ""
                    rejection_badge = " &nbsp;⚠️ *Sent back*" if has_rejection else ""
                    col_info.markdown(
                        f"**{ref}**{rejection_badge} &nbsp;·&nbsp; {row['Portf. name']}{portf_no_part}"
                        f" &nbsp;·&nbsp; {row['Tr. date']}"
                        f" &nbsp;·&nbsp; {row['Tr. description']}"
                        f" &nbsp;·&nbsp; **{row['Amount']} {row['Currency']}**"
                    )

                    if col_btn.button("▲ Close" if is_expanded else "▼ Open", key=f"exp_btn_{ref}"):
                        st.session_state[f"exp_{ref}"] = not is_expanded
                        st.rerun()

                    # ── EXPANDED: individual justification + evidence ──
                    if is_expanded:
                        st.divider()

                        if has_rejection:
                            st.warning(f"⚠️ **Compliance comments:** {row['Compliance_Comments']}")
                            if str(row['Explanation']).strip():
                                st.info(f"💬 **Your previous justification:** {row['Explanation']}")

                        if has_rejection and f"ans_{ref}" not in st.session_state:
                            st.session_state[f"ans_{ref}"] = str(row['Explanation']).strip()
                        ans = st.text_area(
                            "Explanation",
                            key=f"ans_{ref}",
                            placeholder="Enter your justification here..."
                        )
                        up_files = st.file_uploader(
                            "📤 Upload Evidence (optional — multiple files allowed)",
                            accept_multiple_files=True,
                            key=f"up_{ref}"
                        )
                        if st.button("Submit to Compliance", key=f"btn_{ref}", type="primary"):
                            if ans:
                                saved_paths = []
                                if up_files:
                                    trx_folder = os.path.join(get_docs_folder(m_val), ref)
                                    os.makedirs(trx_folder, exist_ok=True)
                                    for i, f_upload in enumerate(up_files):
                                        f_name = f"{ref}_Doc_{i}_{f_upload.name}"
                                        # Truncate filename if full path would exceed Windows MAX_PATH (260)
                                        ext = os.path.splitext(f_name)[1]
                                        max_name = 259 - len(trx_folder) - 1  # 1 for separator
                                        if len(f_name) > max_name:
                                            f_name = f_name[:max_name - len(ext)] + ext
                                        f_path = os.path.join(trx_folder, f_name)
                                        with open(f_path, "wb") as fh:
                                            fh.write(f_upload.getbuffer())
                                        saved_paths.append(f_path)

                                if saved_paths:
                                    b_data.at[idx, 'Doc_Path'] = ";".join(saved_paths)
                                b_data.at[idx, 'Explanation'] = ans
                                b_data.at[idx, 'Resolved'] = "Waiting for Compliance"
                                b_data.at[idx, 'Date of Response'] = datetime.now().strftime("%Y-%m-%d")
                                b_data.to_excel(b_path, index=False)
                                st.success(f"Submitted {ref}")
                                st.session_state[f"exp_{ref}"] = False
                                st.rerun()
                            else:
                                st.error("Justification text is required.")
        else:
            st.success("✅ No pending tasks.")
    else:
        st.info("No Monaco folders found in the directory.")

# ============================================================
# COMPLIANCE DASHBOARD
# ============================================================
else:
    st.title("🕵️ Monaco Compliance Dashboard")
    pwd = st.sidebar.text_input("Compliance Password", type="password")

    if pwd == COMPLIANCE_PASSWORD:
        with st.expander("📁 Step 1: Initialize New Month"):
            m_in = st.text_input("Month (e.g., 2026.01)")
            f_in = st.file_uploader("Upload Expersoft Excel", type="xlsx")
            if m_in and f_in:
                if st.button("Initialize Month"):
                    initialize_files(f_in, m_in)
                    st.success(f"Initialized Monaco_{m_in}"); st.rerun()

        folders = sorted([f for f in os.listdir(BASE_DIR) if f.startswith("Monaco_")], reverse=True)

        if folders:
            sel_month = st.selectbox("Current View", folders)
            m_val = sel_month.split('_')[1]
            file_path = os.path.join(BASE_DIR, sel_month, f"AML Cashflows - Monaco - {m_val} - Reviewed.xlsx")
            data = pd.read_excel(file_path).fillna("")

            if 'Date Resolved' not in data.columns:
                data['Date Resolved'] = ""
            if 'Compliance_Comments' not in data.columns:
                data['Compliance_Comments'] = ""

            data['Tr. date'] = pd.to_datetime(data['Tr. date'], errors='coerce').dt.strftime('%d %b %Y').fillna("")

            # Detect portfolio number column
            portf_num_col = get_portf_num_col(data)

            # Build the list of columns to show in dataframes (conditionally include portfolio number)
            def cols_with_portf(base_cols):
                """Insert portfolio number column right after 'Portf. name' if it exists."""
                if portf_num_col and portf_num_col in data.columns:
                    result = []
                    for c in base_cols:
                        result.append(c)
                        if c == 'Portf. name':
                            result.append(portf_num_col)
                    return result
                return base_cols

            # --- 4 TAB SYSTEM ---
            t1, t2, t3, t4 = st.tabs(["📢 New Alerts", "⏳ Pending RM", "🕵️ Investigation", "✅ Resolved"])

            # ---- TAB 1: NEW ALERTS ----
            with t1:
                new_alerts = data[(data['AML_Flag_Reason'] != "Clear") & (data['Date to RM'] == "")]

                if not new_alerts.empty:
                    st.info("The following alerts have been detected. Group them by RM and send for justification.")

                    for rm in new_alerts['Portf. Manager'].unique():
                        rm_tasks = new_alerts[new_alerts['Portf. Manager'] == rm]

                        with st.expander(f"RM: {rm} ({len(rm_tasks)} Alerts)"):
                            display_cols = cols_with_portf(
                                ['Ref', 'Portf. name', 'Tr. date', 'Amount', 'Tr. description', 'AML_Flag_Reason']
                            )
                            st.dataframe(rm_tasks[[c for c in display_cols if c in rm_tasks.columns]])

                            email = get_rm_email(rm)
                            tasks_str = "\n".join([
                                f"- {r['Ref']}: {r['Portf. name']}"
                                + (f" (Portfolio {r[portf_num_col]})" if portf_num_col else "")
                                + f" ({r['Tr. description']})"
                                for _, r in rm_tasks.iterrows()
                            ])
                            body = urllib.parse.quote(
                                f"Hi {rm},\n\nPlease justify the following transactions in the AML Portal:\n\n{tasks_str}\n\nRegards,"
                            )
                            st.link_button(f"📧 Draft Email to {rm}", f"mailto:{email}?subject=AML Justification Required&body={body}")

                            if st.button("✔️ Mark as Sent to Banker", key=f"send_{rm}"):
                                data.loc[rm_tasks.index, 'Date to RM'] = datetime.now().strftime("%Y-%m-%d")
                                data.to_excel(file_path, index=False)
                                st.success(f"Alerts moved to Pending RM for {rm}")
                                st.rerun()
                else:
                    st.success("All flagged alerts have been sent to RMs.")

            # ---- TAB 2: PENDING RM ----
            with t2:
                st.subheader("⏳ Waiting for Banker Justification")
                pending_rm = data[(data['Date to RM'] != "") & (data['Resolved'] == "No")]

                if not pending_rm.empty:
                    display_cols = cols_with_portf(
                        ['Ref', 'Portf. name', 'Portf. Manager', 'Tr. date', 'Amount', 'Date to RM', 'Tr. description']
                    )
                    st.dataframe(
                        pending_rm[[c for c in display_cols if c in pending_rm.columns]],
                        use_container_width=True
                    )
                else:
                    st.write("No items are currently outstanding with the RMs.")

            # ---- TAB 3: INVESTIGATION ----
            with t3:
                st.subheader("🕵️ Review Submissions")

                # Pending rejection email notifications
                if st.session_state.get('pending_rej_emails'):
                    for ref, email_data in list(st.session_state['pending_rej_emails'].items()):
                        with st.container(border=True):
                            st.warning(f"⚠️ Rejection saved for **{ref}**. Notify the banker:")
                            st.link_button(
                                "📧 Email Rejection to Banker",
                                f"mailto:{email_data['email']}?subject={email_data['subject']}&body={email_data['body']}"
                            )
                            if st.button("✅ Done", key=f"rej_done_{ref}"):
                                del st.session_state['pending_rej_emails'][ref]
                                st.rerun()

                review_data = data[data['Resolved'] == "Waiting for Compliance"]

                if not review_data.empty:
                    for idx, row in review_data.iterrows():
                        with st.container(border=True):
                            st.write(f"### {row['Ref']} - {row['Portf. name']}")

                            # Portfolio number display
                            portf_num_display = (
                                f" | **Portfolio No:** {row[portf_num_col]}" if portf_num_col else ""
                            )
                            st.write(
                                f"🔍 **Transaction:** {row['Tr. description']}"
                                f" | {row['Tr. date']}"
                                f" | {row['Amount']} {row['Currency']}"
                                f"{portf_num_display}"
                            )
                            st.write(f"🚩 **Flag Reason:** {row['AML_Flag_Reason']}")
                            st.write(f"💬 **RM Justification:** {row['Explanation']}")

                            # Multiple document viewer
                            if row['Doc_Path']:
                                paths = str(row['Doc_Path']).split(";")
                                for p in paths:
                                    if p and os.path.exists(p):
                                        f_name = os.path.basename(p)
                                        if st.button(f"📂 Open {f_name}", key=f"view_{p}"):
                                            os.startfile(p)

                            c1, c2 = st.columns([1, 4])
                            if c1.button("✅ Approve", key=f"app_{idx}", type="primary"):
                                st.session_state[f'approving_{row["Ref"]}'] = True

                            if st.session_state.get(f'approving_{row["Ref"]}', False):
                                app_comment = st.text_area(
                                    "Compliance Comment (optional)",
                                    key=f"app_comment_{row['Ref']}",
                                    placeholder="Leave a note for the record, or leave blank..."
                                )
                                if st.button("Confirm Approval", key=f"app_confirm_{row['Ref']}"):
                                    if app_comment:
                                        data.at[idx, 'Compliance_Comments'] = app_comment
                                    data.at[idx, 'Resolved'] = "Yes"
                                    data.at[idx, 'Date Resolved'] = datetime.now().strftime("%Y-%m-%d")
                                    data.to_excel(file_path, index=False)
                                    st.session_state[f'approving_{row["Ref"]}'] = False
                                    st.rerun()

                            if c2.button("❌ Reject / More Info", key=f"rej_{idx}"):
                                st.session_state[f'rejecting_{row["Ref"]}'] = True

                            if st.session_state.get(f'rejecting_{row["Ref"]}', False):
                                rej_reason = st.text_area(
                                    "Rejection Reason / Additional Info Required",
                                    key=f"rej_reason_{row['Ref']}"
                                )
                                if st.button("Submit Rejection", key=f"rej_submit_{row['Ref']}"):
                                    if rej_reason:
                                        data.at[idx, 'Compliance_Comments'] = rej_reason
                                        data.at[idx, 'Resolved'] = "No"
                                        data.to_excel(file_path, index=False)

                                        rm_email = get_rm_email(row['Portf. Manager'])
                                        subject = urllib.parse.quote(f"AML Rejection - {row['Ref']} - {row['Portf. name']}")
                                        portf_line = (
                                            f"Portfolio No: {row[portf_num_col]}\n" if portf_num_col else ""
                                        )
                                        body = urllib.parse.quote(
                                            f"Dear {row['Portf. Manager']},\n\n"
                                            f"Your justification for the following transaction requires additional information:\n\n"
                                            f"Ref: {row['Ref']}\n"
                                            f"Client: {row['Portf. name']}\n"
                                            f"{portf_line}"
                                            f"Transaction: {row['Tr. description']} ({row['Tr. date']})\n\n"
                                            f"Compliance Comments:\n{rej_reason}\n\n"
                                            f"Please update your response in the AML Portal.\n\nRegards,"
                                        )

                                        if 'pending_rej_emails' not in st.session_state:
                                            st.session_state['pending_rej_emails'] = {}
                                        st.session_state['pending_rej_emails'][row['Ref']] = {
                                            'email': rm_email,
                                            'subject': subject,
                                            'body': body
                                        }
                                        st.session_state[f'rejecting_{row["Ref"]}'] = False
                                        st.rerun()
                                    else:
                                        st.warning("Please enter a rejection reason before submitting.")
                else:
                    st.info("No justifications are pending your review.")

            # ---- TAB 4: RESOLVED ----
            with t4:
                st.subheader("✅ Resolved Transactions")
                resolved_data = data[data['Resolved'] == "Yes"]

                if not resolved_data.empty:
                    resolved_display = resolved_data.copy()
                    resolved_display['Explanation'] = resolved_display.apply(
                        lambda r: (
                            f"{r['Explanation']} (compliance comment: {r['Compliance_Comments']})"
                            if str(r.get('Compliance_Comments', '')).strip()
                            else r['Explanation']
                        ),
                        axis=1
                    )
                    base_resolved_cols = [
                        'Ref', 'Portf. name', 'Tr. date', 'Amount', 'Tr. description',
                        'Date to RM', 'Date of Response', 'Explanation', 'Date Resolved'
                    ]
                    display_cols = cols_with_portf(base_resolved_cols)
                    st.dataframe(
                        resolved_display[[c for c in display_cols if c in resolved_display.columns]],
                        use_container_width=True
                    )

                    csv = resolved_data.to_csv(index=False).encode('utf-8')
                    st.download_button("📥 Export Final Report", csv, f"AML_Final_{m_val}.csv", "text/csv")
                else:
                    st.write("No transactions have been fully resolved yet.")

    else:
        st.warning("Please enter the Compliance Password in the sidebar to access the dashboard.")