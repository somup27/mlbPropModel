import streamlit as st
import pickle
import os
from datetime import datetime

PICKLE_PATH = os.path.join(os.getcwd(), "bets.pkl")

# Load existing bets
def load_bets():
    if os.path.exists(PICKLE_PATH):
        with open(PICKLE_PATH, "rb") as f:
            return pickle.load(f)
    return {"ungraded_bets": [], "graded_bets": []}

# Save updated bets
def save_bets(bets):
    with open(PICKLE_PATH, "wb") as f:
        pickle.dump(bets, f)

# --- Page Title ---
st.title("📊 MLB Prop Bet Tracker")

# --- Add Bet Form ---

with st.expander("➕ Add a New Bet"):
    with st.form("bet_form"):
        date = st.date_input("Date", value=datetime.today())
        player = st.text_input("Player Name")
        prop_type = st.selectbox("Prop Type", ["Total Bases", "Strikeouts", "Hits Allowed", "Pitching Outs", "Walks Allowed"])
        prop_line = st.number_input("Prop Line", step=0.1)
        direction = st.radio("Direction", ["Over", "Under"])
        odds = st.text_input("Odds (e.g., -110, +130)")
        stake = st.number_input("Stake ($)", step=0.5, min_value=0.0)
        grade = st.selectbox("Grade (optional)", ["", "W", "L", "P"], index=0)

        submitted = st.form_submit_button("Add Bet")

        if submitted:
            bet = {
                "date": date.strftime("%Y-%m-%d"),
                "player": player,
                "prop_type": prop_type,
                "line": prop_line,
                "direction": direction.lower(),
                "odds": odds,
                "stake": stake,
                "grade": grade if grade else None,
                "timestamp": datetime.now().isoformat()
            }

            bets = load_bets()
            if grade == '' or not grade:
                bets['ungraded_bets'].append(bet)
            else:
                bets['graded_bets'].append(bet)
            save_bets(bets)
            st.success("✅ Bet added successfully!")
            st.rerun()

# --- Grade Ungraded Bets ---
st.header("📝 Grade Ungraded Bets")

bets = load_bets()
ungraded_bets = bets.get("ungraded_bets", [])

if ungraded_bets:
    for i, bet in enumerate(ungraded_bets):
        with st.expander(f"{bet['date']} - {bet['player']} - {bet['prop_type']} ({bet['direction'].capitalize()})"):
            st.markdown(f"""
            - **Line:** {bet['line']}  
            - **Odds:** {bet['odds']}  
            - **Stake:** ${bet['stake']}  
            - **Timestamp:** {bet['timestamp']}
            """)
            grade_choice = st.selectbox(
                f"Grade for bet {i+1}", ["", "W", "L", "P"], key=f"grade_select_{i}"
            )
            if grade_choice:
                if st.button(f"✅ Submit Grade for Bet {i+1}", key=f"submit_grade_{i}"):
                    # Move bet from ungraded to graded
                    bet["grade"] = grade_choice
                    bets['graded_bets'].append(bet)
                    bets['ungraded_bets'].pop(i)
                    save_bets(bets)
                    st.success(f"Bet graded as {grade_choice}")
                    st.rerun()
else:
    st.info("No ungraded bets currently available.")

# --- Calculate Total Profit ---
def calculate_profit(bet):
    if bet["grade"] == "L":
        return -bet["stake"]
    elif bet["grade"] == "P":
        return 0
    elif bet["grade"] == "W":
        odds_str = bet["odds"].replace("+", "")
        try:
            odds = int(odds_str)
            if bet["odds"].startswith('+'):
                return bet["stake"] * (odds / 100)
            elif bet["odds"].startswith('-'):
                return bet["stake"] * (100 / abs(odds))
        except:
            return 0  # Fallback for invalid odds format
    return 0

# Compute total profit
total_profit = sum(calculate_profit(bet) for bet in bets.get("graded_bets", []))

# Display profit
st.markdown("### 💰 To-Date Profit")
st.metric(label="Profit", value=f"${total_profit:,.2f}")

# --- Graded Bet History (Toggleable) ---
with st.expander("📚 Show Graded Bet History"):
    graded_bets = bets.get("graded_bets", [])
    if graded_bets:
        for bet in sorted(graded_bets, key=lambda x: x['date'], reverse=True):
            st.markdown(f"""
            **{bet['date']} - {bet['player']}**  
            - Prop: {bet['prop_type']} ({bet['direction'].capitalize()})  
            - Line: {bet['line']}  
            - Odds: {bet['odds']}  
            - Stake: ${bet['stake']}  
            - Grade: **{bet['grade']}**  
            - Timestamp: {bet['timestamp']}  
            ---
            """)
    else:
        st.info("No graded bets yet.")