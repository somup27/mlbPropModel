import streamlit as st
import pandas as pd
from pybaseball import statcast, playerid_lookup
import requests
import time

mlb_team_abbreviations = {
    "Arizona Diamondbacks": "AZ",
    "Atlanta Braves": "ATL",
    "Baltimore Orioles": "BAL",
    "Boston Red Sox": "BOS",
    "Chicago White Sox": "CWS",
    "Chicago Cubs": "CHC",
    "Cincinnati Reds": "CIN",
    "Cleveland Guardians": "CLE",
    "Colorado Rockies": "COL",
    "Detroit Tigers": "DET",
    "Houston Astros": "HOU",
    "Kansas City Royals": "KC",
    "Los Angeles Angels": "LAA",
    "Los Angeles Dodgers": "LAD",
    "Miami Marlins": "MIA",
    "Milwaukee Brewers": "MIL",
    "Minnesota Twins": "MIN",
    "New York Mets": "NYM",
    "New York Yankees": "NYY",
    "Athletics": "ATH",
    "Philadelphia Phillies": "PHI",
    "Pittsburgh Pirates": "PIT",
    "San Diego Padres": "SD",
    "San Francisco Giants": "SF",
    "Seattle Mariners": "SEA",
    "St. Louis Cardinals": "STL",
    "Tampa Bay Rays": "TB",
    "Texas Rangers": "TEX",
    "Toronto Blue Jays": "TOR",
    "Washington Nationals": "WSH"
}


def get_player_id(name):
    try:
        first, last = name.split()
        id_data = playerid_lookup(last, first, fuzzy=True)
        return int(id_data['key_mlbam'].iloc[0]) if not id_data.empty else None
    except:
        return None

def get_player_info(mlbam_id):
    url = f'https://statsapi.mlb.com/api/v1/people/{mlbam_id}?hydrate=teams,currentTeam'
    response = requests.get(url)
    time.sleep(0.5)
    data = response.json()
    if 'people' in data and len(data['people']) > 0:
        player = data['people'][0]
        return {
            'name': player.get('fullName'),
            'team': player.get('currentTeam', {}).get('name', 'Unknown'),
            'position': player.get('primaryPosition', {}).get('name', 'Unknown')
        }
    return {'name': 'Unknown', 'team': 'Unknown', 'position': 'Unknown'}

def batter_lines_today():
    headers = {
        "accept": "application/json",  # changed to expect JSON response
        "accept-encoding": "gzip, deflate, br, zstd",
        "accept-language": "en-US,en;q=0.9",
        "cache-control": "max-age=0",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
        "upgrade-insecure-requests": "1",
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "none",
        "sec-fetch-user": "?1",
        "sec-ch-ua": '"Chromium";v="136", "Google Chrome";v="136", "Not.A/Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
    }

    def safe_int(s):
        return int(s.replace('−', '-').replace('+', ''))

    urls = {
        'Total Bases': 'https://sportsbook-nash.draftkings.com/api/sportscontent/dkusdc/v1/leagues/84240/categories/743/subcategories/6607',
    }

    batter_data = []
    opp_pitcher_dict = {}

    tbResponse = requests.get(urls['Total Bases'], headers=headers, timeout=5)
    time.sleep(2)
    if tbResponse.status_code != 200:
        print(f"Failed to fetch Event data. Status code: {tbResponse.status_code}")
        return None
    tbJSON = tbResponse.json()

    for event in tbJSON['events']:
        if 'startingPitcherPlayerName' in event['participants'][0]['metadata']:
            opp_pitcher_dict[event['participants'][1]['metadata']['shortName']] = event['participants'][0]['metadata']['startingPitcherPlayerName']
        if 'startingPitcherPlayerName' in event['participants'][1]['metadata']:
            opp_pitcher_dict[event['participants'][0]['metadata']['shortName']] = event['participants'][1]['metadata']['startingPitcherPlayerName']

    jsons = [tbJSON]
    type = ['Total Bases']

    for i in range(len(jsons)):
        for selection in jsons[i]['selections']:
            if selection['label'].lower() == 'under':
                continue
            if selection['points'] < 1.5 and int(safe_int(selection['displayOdds']['american'])) < -150:
                continue
            batter_name = selection['participants'][0]['name']

            bid = get_player_id(batter_name)
            if not bid:
                continue
            batter_profile = get_player_info(bid)
            if batter_profile['team'] not in mlb_team_abbreviations or mlb_team_abbreviations[batter_profile['team']] not in opp_pitcher_dict:
                continue
            opp_pitcher_name = opp_pitcher_dict[mlb_team_abbreviations[batter_profile['team']]]
            opp_pid = get_player_id(opp_pitcher_name)
            if not opp_pid:
                continue
            line = selection['points']
            label = selection['label']
            odds = selection['displayOdds']['american']

            batter_data.append({
                'batter_name': batter_name,
                'team': mlb_team_abbreviations[batter_profile['team']],
                'batter_id': bid,
                'opp_pid': opp_pid,
                'label': label,
                'line': line,
                'odds': odds,
                'type': type[i]
            })

    return pd.DataFrame(batter_data)

def evaluate_tb_rules(batter_df, pitcher_df, pitcher_hand='R', batter_hand='L', tb_prop_line=1.5, lookback_games=10):
    # Assign Total Bases based on event
    def calculate_total_bases(events):
        return {
            'single': 1, 'double': 2,
            'triple': 3, 'home_run': 4
        }.get(events, 0)

    try:

        batter_df['TB'] = batter_df['events'].apply(calculate_total_bases)

        # Aggregate TB to game level
        game_tb = (
            batter_df.groupby(['game_date'])['TB']
            .sum()
            .reset_index()
            .sort_values('game_date', ascending=False)
        )

        recent_games = game_tb.head(lookback_games)
        recent_tb = recent_games['TB']

        ## Rule 1: Hit Rate Over Line
        hit_rate = (recent_tb > tb_prop_line).mean()
        rule_1 = hit_rate >= 0.65

        ## Rule 2: Rolling Avg TB
        rolling_avg = recent_tb.mean()
        rule_2 = rolling_avg >= (tb_prop_line + 0.25)

        ## Rule 3: TB vs Pitcher Handedness
        split_df = batter_df[batter_df['p_throws'] == pitcher_hand]
        split_game_tb = split_df.groupby('game_date')['TB'].sum()
        rule_3 = split_game_tb.mean() >= (tb_prop_line + 0.25) if not split_game_tb.empty else False

        ## Rule 4: xSLG or ISO
        batted_ball_events = split_df[split_df['bb_type'].notnull()]
        batted_ball_events['iso'] = batted_ball_events['estimated_slg_using_speedangle'] - batted_ball_events['estimated_ba_using_speedangle']
        rule_4 = (
            batted_ball_events['estimated_slg_using_speedangle'].mean() >= 0.450 or
            batted_ball_events['iso'].mean() >= 0.180
        )

        ## Rule 5: Pitcher Weakness vs Batter Handedness
        pitcher_split = pitcher_df[pitcher_df['stand'] == batter_hand]

        # TB allowed by pitcher: calculate from events
        pitcher_split['TB_allowed'] = pitcher_split['events'].apply(calculate_total_bases)

        # xSLG allowed estimate (mean over all BIP events)
        xslg_allowed = pitcher_split[pitcher_split['bb_type'].notnull()]['estimated_slg_using_speedangle'].mean()
        tb_per_pa = pitcher_split.groupby(['game_date', 'batter'])['TB_allowed'].sum().mean()

        rule_5 = (xslg_allowed >= 0.450 or tb_per_pa >= 1.0)

        # Compile rule results
        rule_results = {
            'rule_1_hit_rate': rule_1,
            'rule_2_rolling_avg_tb': rule_2,
            'rule_3_vs_hand_split': rule_3,
            'rule_4_xslg_or_iso': rule_4,
            'rule_5_pitcher_weakness': rule_5
        }

        rules = {
            'hit_rate': hit_rate,
            'rolling_avg_tb': rolling_avg,
            'vs_hand_split': split_game_tb.mean(),
            'avg_xslg': batted_ball_events['estimated_slg_using_speedangle'].mean(),
            'avg_iso': batted_ball_events['iso'].mean(),
            'pitcher_xslg_allowed': xslg_allowed,
            'pitcher_tb_allowed_per_pa': tb_per_pa
        }

        score = sum(rule_results.values())
        rules['score'] = score
        rules['recommend'] = score >= 4

        return rules
    except:
        return None


st.title("MLB Batter Props")

with st.spinner("Loading data..."):
    props_df = batter_lines_today()
    statcast_df = statcast('2025-03-27', '2025-05-06')

evaluated = []
with st.spinner("Evaluating batter props..."):
    for _, row in props_df.iterrows():
        batter_name, team, bid, opp_pid, label, line, odds, type = row['batter_name'], row['team'], row['batter_id'], row['opp_pid'], row['label'], row['line'], row['odds'], row['type']
        batter_df = statcast_df[statcast_df['batter'] == bid]
        if batter_df.empty: continue
        pitcher_df = statcast_df[statcast_df['pitcher'] == opp_pid]
        pitcher_df = pitcher_df.sort_values(by=['game_date', 'at_bat_number', 'pitch_number'])
        if pitcher_df.empty: continue
        result = evaluate_tb_rules(batter_df, pitcher_df, pitcher_df['p_throws'].iloc[0], batter_df['stand'].iloc[0], line)
        if not result: continue

        evaluated.append({
            'Batter': batter_name,
            'Team': team,
            'Prop': type,
            'Line': line,
            'Odds': odds,
            'Direction': label,
            'Rolling Average Total Bases (Last 10 Games)': result['rolling_avg_tb'],
            'Avg Total Bases vs. Hand (Last 10 Games)': result['vs_hand_split'],
            'Avg xSLG': result['avg_xslg'],
            'Avg ISO': result['avg_iso'],
            'Pitcher xSLG Allowed': result['pitcher_xslg_allowed'],
            'Pitcher Total Bases Allowed per PA': result['pitcher_tb_allowed_per_pa'],
            'Total Bases Hit Rate (L10)': result['hit_rate'],
            'Rules Hit': result['score'],
            'Recommendation': 'Target' if result['score'] >= 4 else 'Pass'
        })

final_df = pd.DataFrame(evaluated)
st.dataframe(final_df, use_container_width=True)

if not final_df.empty:
    st.subheader("Top Picks (5/5 Matching Rules)")
    st.dataframe(final_df[final_df['Rules Hit'] == 5], use_container_width=True)

if not final_df.empty:
    st.subheader("Top Picks (4/5 Matching Rules)")
    st.dataframe(final_df[final_df['Rules Hit'] == 4], use_container_width=True)