# Initial canvas setup - starting point for Fantasy Football Owner Score App
# This file will be extended incrementally

import streamlit as st
import requests
import pandas as pd
import os

st.set_page_config(page_title="Dynasty Owner Score Tracker")
st.title("Dynasty Owner Score Tracker")

# START: Load KTC Values from CSV
# START: Updated file path for local environment
ktc_csv_path = "ktc_values (1).csv"
# END
if os.path.exists(ktc_csv_path):
    ktc_df = pd.read_csv(ktc_csv_path)
    st.success("KTC values loaded successfully.")
else:
    ktc_df = pd.DataFrame()
    st.warning("KTC values file not found.")
# END

# Placeholder header
st.header("🏈 Track Dynasty Owner Scores Based on Trade Wins & Standings")

# START: Allow user to select league from their Sleeper username
sleeper_username = st.text_input("Enter your Sleeper username")
league_id = None

if sleeper_username:
    user_resp = requests.get(f"https://api.sleeper.app/v1/user/{sleeper_username}")
    if user_resp.status_code == 200:
        user_id = user_resp.json().get("user_id")
        leagues_resp = requests.get(f"https://api.sleeper.app/v1/user/{user_id}/leagues/nfl/2024")
        if leagues_resp.status_code == 200:
            leagues = leagues_resp.json()
            league_options = {f"{lg['name']} ({lg['league_id']})": lg['league_id'] for lg in leagues}
            selected_league = st.selectbox("Select a league", list(league_options.keys()))
            league_id = league_options[selected_league]
    else:
        st.error("Sleeper username not found or could not be accessed.")
# END

# START: Load all transactions from all weeks and previous leagues
@st.cache_data(show_spinner=False)
def get_all_transactions(league_id):
    all_trades = []
    current_league_id = league_id
    visited = set()

    while current_league_id and current_league_id not in visited:
        visited.add(current_league_id)

        # Loop through all 18 weeks for this league ID
        for week in range(0, 19):
            url = f"https://api.sleeper.app/v1/league/{current_league_id}/transactions/{week}"
            response = requests.get(url)
            if response.status_code == 200:
                transactions = response.json()
                trades = [t for t in transactions if t.get("type") == "trade"]
                all_trades.extend(trades)

        # Move to previous league ID (if exists)
        league_info = requests.get(f"https://api.sleeper.app/v1/league/{current_league_id}")
        if league_info.status_code == 200:
            league_data = league_info.json()
            current_league_id = league_data.get("previous_league_id")
        else:
            break

    return all_trades
# END

# START: Get owner ID to username mapping
@st.cache_data(show_spinner=False)
def get_owner_map(league_id):
    url = f"https://api.sleeper.app/v1/league/{league_id}/users"
    response = requests.get(url)
    if response.status_code == 200:
        users = response.json()
        return {user["user_id"]: user["display_name"] for user in users}
    return {}
# END

# START: Parse trades and calculate win values
@st.cache_data(show_spinner=False)
def evaluate_trades(trades, ktc_df):
    owner_scores = {}
    for trade in trades:
        rosters = trade.get("roster_ids", [])
        adds = trade.get("adds") or {}  # Safely handle None

        trade_map = {rid: [] for rid in rosters}
        for player_id, rid in adds.items():
            trade_map[rid].append(player_id)

        values = {}
        for rid, players in trade_map.items():
            total_value = 0
            for p in players:
                player_name = p.replace("_", " ").title()
                ktc_row = ktc_df[ktc_df["Player_Sleeper"].str.lower() == player_name.lower()]
                if not ktc_row.empty:
                    total_value += int(ktc_row["KTC_Value"].values[0])
            values[rid] = total_value

        if len(values) == 2:
            (a, b), (va, vb) = list(values.items())[0], list(values.items())[1]
            winner = a if va > vb else b
            diff = abs(va - vb)
            owner_scores[winner] = owner_scores.get(winner, 0) + diff

    return owner_scores
# END

if league_id:
    trades = get_all_transactions(league_id)
    st.write(f"Found {len(trades)} trades in league {league_id} and prior seasons.")

    if not ktc_df.empty and trades:
        owner_scores = evaluate_trades(trades, ktc_df)
        owner_map = get_owner_map(league_id)

        # Convert to usernames
        # START: Convert roster ID to user display name via lookup
        # We'll need to query rosters to get the mapping of roster_id -> owner_id
        roster_resp = requests.get(f"https://api.sleeper.app/v1/league/{league_id}/rosters")
        roster_map = {}
        if roster_resp.status_code == 200:
            for r in roster_resp.json():
                roster_map[r["roster_id"]] = r["owner_id"]

        readable_scores = []
        for rid, owner_id in roster_map.items():
            display_name = owner_map.get(owner_id, f"User {owner_id}")
            score = owner_scores.get(rid, 0)
            readable_scores.append((display_name, score))
        # END

        st.subheader("📈 Trade Scoreboard")
        df = pd.DataFrame(readable_scores, columns=["Owner", "Score"]).sort_values(by="Score", ascending=False).reset_index(drop=True)
        st.dataframe(df, use_container_width=True, height=len(df) * 35 + 40)

# START: Global leaderboard from usernames.csv
user_csv_path = "sleeper_usernames.csv"
if os.path.exists(user_csv_path):
    st.subheader("🌍 Global Leaderboard (Multi-League)")
    usernames_df = pd.read_csv(user_csv_path)
    global_scores = []

    for username in usernames_df["sleeper_username"]:
        user_resp = requests.get(f"https://api.sleeper.app/v1/user/{username}")
        if user_resp.status_code != 200:
            continue

        user_id = user_resp.json().get("user_id")
        leagues_resp = requests.get(f"https://api.sleeper.app/v1/user/{user_id}/leagues/nfl/2024")
        if leagues_resp.status_code != 200:
            continue

        user_score = 0
        for league in leagues_resp.json():
            lid = league["league_id"]
            trades = get_all_transactions(lid)
            owner_scores = evaluate_trades(trades, ktc_df)
            roster_resp = requests.get(f"https://api.sleeper.app/v1/league/{lid}/rosters")
            if roster_resp.status_code == 200:
                for r in roster_resp.json():
                    if r["owner_id"] == user_id:
                        score = owner_scores.get(r["roster_id"], 0)
                        user_score += score

        global_scores.append((username, user_score))

    global_df = pd.DataFrame(global_scores, columns=["Sleeper Username", "Total Score"]).sort_values(by="Total Score", ascending=False).reset_index(drop=True)
    st.dataframe(global_df, use_container_width=True, height=len(global_df) * 35 + 40)
# END
st.write("Owner scores will appear here after implementing trade tracking and KTC integration.")
