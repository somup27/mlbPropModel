# -- Imports and Setup --
import streamlit as st
import pandas as pd
import time
from pybaseball import statcast, playerid_lookup
import requests

# ---------------------- Utility Functions ----------------------

def pitcher_lines_today():
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

    urls = {
        'Hits Allowed': 'https://sportsbook-nash.draftkings.com/api/sportscontent/dkusdc/v1/leagues/84240/categories/1031/subcategories/9886',
        'Strikeouts': 'https://sportsbook-nash.draftkings.com/api/sportscontent/dkusdc/v1/leagues/84240/categories/1031/subcategories/15221',
        'Pitching Outs': 'https://sportsbook-nash.draftkings.com/api/sportscontent/dkusdc/v1/leagues/84240/categories/1031/subcategories/17413',
        'Walks Allowed': 'https://sportsbook-nash.draftkings.com/api/sportscontent/dkusdc/v1/leagues/84240/categories/1031/subcategories/15219'
    }

    pitcher_data = []
    pitcher_keys = []

    kResponse = requests.get(urls['Strikeouts'], headers=headers, timeout=5)
    time.sleep(2)
    if kResponse.status_code != 200:
        print(f"Failed to fetch Event data. Status code: {kResponse.status_code}")
        return None
    kJSON = kResponse.json()

    for event in kJSON['events']:
        if 'startingPitcherPlayerName' in event['participants'][0]['metadata']:
            pitcher_keys.append((event['participants'][0]['metadata']['startingPitcherPlayerName'], event['participants'][1]['metadata']['shortName']))
        if 'startingPitcherPlayerName' in event['participants'][1]['metadata']:
            pitcher_keys.append((event['participants'][1]['metadata']['startingPitcherPlayerName'], event['participants'][0]['metadata']['shortName']))
    pitcher_dict = {pitcher: opponent for pitcher, opponent in pitcher_keys}

    poResponse = requests.get(urls['Pitching Outs'], headers=headers, timeout=5)
    time.sleep(2)
    if poResponse.status_code != 200:
        print(f"Failed to fetch Event data. Status code: {poResponse.status_code}")
        poJSON = {'selections': []}
    else:
        poJSON = poResponse.json()

    haResponse = requests.get(urls['Hits Allowed'], headers=headers, timeout=5)
    time.sleep(2)
    if haResponse.status_code != 200:
        print(f"Failed to fetch Event data. Status code: {haResponse.status_code}")
        haJSON = {'selections': []}
    else:
        haJSON = haResponse.json()

    waResponse = requests.get(urls['Walks Allowed'], headers=headers, timeout=5)
    if waResponse.status_code != 200:
        print(f"Failed to fetch Event data. Status code: {waResponse.status_code}")
        waJSON = {'selections': []}
    else:
        waJSON = waResponse.json()


    selections = [kJSON, poJSON, haJSON, waJSON]
    type = ['Strikeouts', 'Pitching Outs', 'Hits Allowed', 'Walks Allowed']

    for i in range(len(selections)):
        for selection in selections[i]['selections']:
            pitcher_name = selection['participants'][0]['name']
            opponent = pitcher_dict.get(pitcher_name, 'Unknown')
            line = selection['points']
            label = selection['label']
            odds = selection['displayOdds']['american']

            pitcher_data.append({
                'pitcher_name': pitcher_name,
                'opponent': opponent,
                'label': label,
                'line': line,
                'odds': odds,
                'type': type[i]
            })

    return pd.DataFrame(pitcher_data)


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
    data = response.json()
    if 'people' in data and len(data['people']) > 0:
        player = data['people'][0]
        return {
            'name': player.get('fullName'),
            'team': player.get('currentTeam', {}).get('name', 'Unknown'),
            'position': player.get('primaryPosition', {}).get('name', 'Unknown')
        }
    return {'name': 'Unknown', 'team': 'Unknown', 'position': 'Unknown'}


def compute_k9(df):
    outs_map = {
        'strikeout': 1, 'field_out': 1, 'force_out': 1, 'sac_bunt': 1, 'sac_fly': 1, 'double_play': 2,
        'grounded_into_double_play': 2, 'strikeout_double_play': 2, 'sac_fly_double_play': 2, 'triple_play': 3,
        'fielders_choice_out': 1
    }
    total_outs = df[df['events'].isin(outs_map)]['events'].map(outs_map).sum()
    innings_pitched = total_outs / 3 if total_outs else 0
    strikeouts = (df['events'] == 'strikeout').sum()
    return (strikeouts / innings_pitched * 9) if innings_pitched > 0 else 0


def compute_total_outs(df):
    outs_map = {
        'strikeout': 1, 'field_out': 1, 'force_out': 1, 'sac_bunt': 1, 'sac_fly': 1, 'double_play': 2,
        'grounded_into_double_play': 2, 'strikeout_double_play': 2, 'sac_fly_double_play': 2, 'triple_play': 3,
        'fielders_choice_out': 1
    }
    return df[df['events'].isin(outs_map)]['events'].map(outs_map).sum()


def evaluate_pitcher_strikeout_prop(df, pitcher_id, opp_team, hand, k_line):
    pitcher_df = df[df['pitcher'] == pitcher_id]
    if pitcher_df.empty or pitcher_df['game_date'].nunique() < 3:
        return None

    pitcher_df = pitcher_df.sort_values(by=['game_date', 'at_bat_number', 'pitch_number'])
    recent_dates = pitcher_df['game_date'].unique()[-3:]
    recent_df = pitcher_df[pitcher_df['game_date'].isin(recent_dates)]

    season_k9 = compute_k9(pitcher_df)
    rolling_k9 = compute_k9(recent_df)
    pitch_counts = recent_df.groupby("game_pk").size()
    median_pitch_count = pitch_counts.median()

    opp_df = df[((df['home_team'] == opp_team) & (df['inning_topbot'] == 'Bottom')) | ((df['away_team'] == opp_team) & (df['inning_topbot'] == 'Top'))]
    opp_df = opp_df[opp_df['p_throws'] == hand]
    strikeouts = (opp_df['events'] == 'strikeout').sum()
    opp_pas = opp_df['batter'].ne(opp_df['batter'].shift()).sum()
    opp_k_pct = strikeouts / opp_pas if opp_pas else 0

    game_strikeouts = pitcher_df[pitcher_df["events"] == "strikeout"].groupby("game_pk").size()
    hit_games = (game_strikeouts >= k_line).sum()
    total_games = pitcher_df['game_pk'].nunique()
    hit_rate = hit_games / total_games if total_games else 0

    rules = {
        'season_k9': season_k9,
        'rolling_k9': rolling_k9,
        'opp_k_pct': opp_k_pct,
        'median_pitch_count': median_pitch_count,
        'hit_rate': hit_rate,
    }

    rules_hit = [
        season_k9 > 9.0,
        rolling_k9 > 9.5,
        opp_k_pct > 0.24,
        median_pitch_count >= 85,
        hit_rate >= 0.65
    ]

    rules_miss = [
        season_k9 < 8.0,
        rolling_k9 < 8.0,
        opp_k_pct < 0.21,
        median_pitch_count < 80,
        hit_rate < 0.35
    ]

    return {
        'rules': rules,
        'rules_hit': sum(rules_hit),
        'rules_miss': sum(rules_miss)
    }


def evaluate_pitching_out_prop(pitcher_data, full_season_data, opp_team, pitching_outs_line, throwing_hand, direction='over'):
    season_total_outs = compute_total_outs(pitcher_data)
    season_starts = len(pitcher_data['game_pk'].unique())
    season_outs_per_start = season_total_outs / season_starts if season_starts > 0 else 0

    recent_dates = pitcher_data['game_date'].unique()[-3:]
    recent_data = pitcher_data[pitcher_data['game_date'].isin(recent_dates)]
    rolling_outs3 = compute_total_outs(recent_data) / 3 if not recent_data.empty else 0

    pitch_counts = recent_data.groupby("game_pk").size()
    avg_pitch_count_3 = pitch_counts.median() if not pitch_counts.empty else 0

    opp_side = full_season_data[
        ((full_season_data['home_team'] == opp_team) & (full_season_data['inning_topbot'] == 'Bottom')) |
        ((full_season_data['away_team'] == opp_team) & (full_season_data['inning_topbot'] == 'Top'))
    ]
    opp_split = opp_side[opp_side['p_throws'] == throwing_hand]
    if not opp_split.empty:
        opp_hits = opp_split['events'].isin(['single', 'double', 'triple', 'home_run']).sum()
        opp_walks = opp_split['events'].isin(['walk', 'hit_by_pitch']).sum()
        batters_faced = opp_split['batter'].ne(opp_split['batter'].shift()).sum()
        opp_ip = batters_faced / 3 if batters_faced > 0 else 0
        opp_whip = (opp_hits + opp_walks) / opp_ip if opp_ip > 0 else 2.0
    else:
        opp_whip = 2.0

    # --- 5. Hit Rate vs Line ---
    outs_per_game = pitcher_data.groupby('game_pk')['events'].apply(lambda x: x.isin([
        'strikeout', 'field_out', 'force_out', 'sac_bunt', 'sac_fly',
        'double_play', 'grounded_into_double_play', 'strikeout_double_play',
        'sac_fly_double_play', 'triple_play', 'fielders_choice_out'
    ]).sum())
    hit_games = (outs_per_game >= pitching_outs_line)
    hit_rate = hit_games.sum() / len(outs_per_game) if len(outs_per_game) > 0 else 0


    if direction == 'over':
        rules = [
            season_outs_per_start > pitching_outs_line,
            rolling_outs3 > pitching_outs_line,
            avg_pitch_count_3 >= 85,
            hit_rate >= .65,
            opp_whip <= 1.11
        ]
    else:
        rules = [
            season_outs_per_start < pitching_outs_line,
            rolling_outs3 < pitching_outs_line,
            avg_pitch_count_3 <= 83,
            hit_rate <= .35,
            opp_whip >= 1.35
        ]

    return {
        "season_outs_per_start": round(season_outs_per_start, 2),
        "rolling_outs3": round(rolling_outs3, 2),
        "avg_pitch_count_3": round(avg_pitch_count_3, 1),
        "outs_hit_rate": round(hit_rate, 2),
        "opp_whip": round(opp_whip, 2),
        "rule_pass_count": sum(rules),
        "rule_results": rules
    }

def evaluate_hits_allowed_prop(pitcher_data, full_season_data, opp_team, hits_line, throwing_hand, direction='over'):
    # --- 1. Season H/9 ---
    total_hits = (pitcher_data['events'].isin(['single', 'double', 'triple', 'home_run'])).sum()
    total_outs = compute_total_outs(pitcher_data)
    ip = total_outs / 3
    season_h9 = (total_hits / ip) * 9 if ip > 0 else 0

    # --- 2. Rolling H/9 (Last 3 starts) ---
    recent_dates = pitcher_data['game_date'].unique()[-3:]
    recent_data = pitcher_data[pitcher_data['game_date'].isin(recent_dates)]
    recent_hits = (recent_data['events'].isin(['single', 'double', 'triple', 'home_run'])).sum()
    recent_outs = compute_total_outs(recent_data)
    recent_ip = recent_outs / 3
    rolling_h9 = (recent_hits / recent_ip) * 9 if recent_ip > 0 else 0

    # --- 3. Median Hits Allowed (Last 3 games) ---
    hits_by_game = recent_data[recent_data['events'].isin(['single', 'double', 'triple', 'home_run'])].groupby('game_pk').size()
    median_hits_allowed = hits_by_game.median() if not hits_by_game.empty else 0

    # --- 4. Opponent Batting Avg vs Hand ---
    opp_data = full_season_data[
        ((full_season_data['home_team'] == opp_team) & (full_season_data['inning_topbot'] == 'Bottom')) |
        ((full_season_data['away_team'] == opp_team) & (full_season_data['inning_topbot'] == 'Top'))
    ]
    opp_vs_hand = opp_data[opp_data['p_throws'] == throwing_hand]
    opp_hits = opp_vs_hand['events'].isin(['single', 'double', 'triple', 'home_run']).sum()
    opp_at_bats = opp_vs_hand['events'].isin(['single', 'double', 'triple', 'home_run', 'strikeout', 'field_out', 'force_out', 'double_play', 'grounded_into_double_play', 'strikeout_double_play', 'fielders_choice_out', 'sac_fly_double_play', 'triple_play']).sum()
    opp_avg_vs_hand = opp_hits / opp_at_bats if opp_at_bats > 0 else 0.25  # fallback

    # --- 5. Hit Rate vs Line ---
    game_hits = pitcher_data[pitcher_data['events'].isin(['single', 'double', 'triple', 'home_run'])].groupby('game_pk').size()
    hit_games = (game_hits >= hits_line)
    hit_rate = hit_games.sum() / len(game_hits) if len(game_hits) > 0 else 0

    # --- Rule Evaluation ---
    rules = [
        season_h9 > 8.5,
        rolling_h9 > 8.8,
        median_hits_allowed >= hits_line,
        opp_avg_vs_hand >= 0.255,
        hit_rate >= 0.65
    ]

    if direction == 'under':
        rules = [
            season_h9 < 7.5,
            rolling_h9 < 7.2,
            median_hits_allowed < hits_line,
            opp_avg_vs_hand <= 0.24,
            hit_rate <= 0.35
        ]

    return {
        "season_h9": round(season_h9, 2),
        "rolling_h9": round(rolling_h9, 2),
        "median_hits_allowed": round(median_hits_allowed, 1),
        "opp_avg_vs_hand": round(opp_avg_vs_hand, 3),
        "ha_hit_rate": round(hit_rate, 2),
        "rule_pass_count": sum(rules),
        "rule_results": rules
    }

def evaluate_walks_allowed(statcast_df, pitcher_id, opp_team, hand, walks_line, direction='over'):
    pitcher_df = statcast_df[statcast_df['pitcher'] == pitcher_id]
    if pitcher_df.empty or pitcher_df['game_date'].nunique() < 3:
        return None

    pitcher_df = pitcher_df.sort_values(by=['game_date', 'at_bat_number', 'pitch_number'])
    recent_dates = pitcher_df['game_date'].unique()[-3:]
    recent_df = pitcher_df[pitcher_df['game_date'].isin(recent_dates)]

    # Calculate BB/9
    def compute_bb9(df):
        walks = (df['events'] == 'walk').sum()
        outs = compute_total_outs(df)
        innings_pitched = outs / 3 if outs else 0
        return (walks / innings_pitched * 9) if innings_pitched > 0 else 0

    season_bb9 = compute_bb9(pitcher_df)
    rolling_bb9 = compute_bb9(recent_df)

    # Median walks allowed over last 3 starts
    walks_per_game = pitcher_df[pitcher_df['events'] == 'walk'].groupby('game_pk').size()
    median_walks_L3 = walks_per_game[-3:].median() if not walks_per_game.empty else 0

    # Opponent BB% vs hand
    opp_df = statcast_df[((statcast_df['home_team'] == opp_team) & (statcast_df['inning_topbot'] == 'Bottom')) |
                          ((statcast_df['away_team'] == opp_team) & (statcast_df['inning_topbot'] == 'Top'))]
    opp_vs_hand = opp_df[opp_df['p_throws'] == hand]
    opp_walks = (opp_vs_hand['events'] == 'walk').sum()
    opp_pas = opp_vs_hand['batter'].ne(opp_vs_hand['batter'].shift()).sum()
    opp_bb_pct = opp_walks / opp_pas if opp_pas else 0

    # Hit Rate
    total_games = pitcher_df['game_pk'].nunique()
    hit_games = (walks_per_game >= walks_line).sum()
    hit_rate = hit_games / total_games if total_games else 0

    # Rule application
    if direction == 'over':
        rules = [
            season_bb9 > 3.2,
            rolling_bb9 > 3.6,
            median_walks_L3 >= walks_line,
            opp_bb_pct > 0.09,
            hit_rate >= 0.65
        ]
    else:
        rules = [
            season_bb9 < 2.2,
            rolling_bb9 < 2.4,
            median_walks_L3 < walks_line,
            opp_bb_pct < 0.075,
            hit_rate <= 0.35
        ]

    return {
        'rules': {
            "season_bb9": round(season_bb9, 2),
            "rolling_bb9": round(rolling_bb9, 2),
            "median_walks_L3": median_walks_L3,
            "opp_bb_pct": round(opp_bb_pct, 3),
            "walks_hit_rate": round(hit_rate, 2)
        },
        'rule_pass_count': sum(rules)
    }


# ---------------------- Streamlit UI ----------------------

st.title("MLB Pitcher Props")

with st.spinner("Loading data..."):
    props_df = pitcher_lines_today()
    statcast_df = statcast('2025-03-27', '2025-05-06')

evaluated = []
with st.spinner("Evaluating pitcher props..."):
    for _, row in props_df.iterrows():
        name, opp, label, line, odds, type = row['pitcher_name'], row['opponent'], row['label'], row['line'], row['odds'], row['type']
        if opp == "A's": opp = 'ATH'
        if opp == 'ARI': opp = 'AZ'
        if opp == 'WAS': opp = 'WSH'
        pid = get_player_id(name)
        if not pid:
            continue
        pitcher_data = statcast_df[statcast_df['pitcher'] == pid]
        pitcher_data = pitcher_data.sort_values(by=['game_date', 'at_bat_number', 'pitch_number'])
        if pitcher_data.empty:
            continue
        hand = pitcher_data['p_throws'].iloc[0]
        profile = get_player_info(pid)
        team = profile['team']

        if type == 'Walks Allowed':
            result = evaluate_walks_allowed(statcast_df, pid, opp, hand, line, direction=label.lower())
        elif type == 'Pitching Outs':
            result = evaluate_pitching_out_prop(pitcher_data, statcast_df, opp, line, hand, direction=label.lower())
        elif type == 'Strikeouts':
            result = evaluate_pitcher_strikeout_prop(statcast_df, pid, opp, hand, line)
        else:
            result = evaluate_hits_allowed_prop(pitcher_data, statcast_df, opp, line, hand, direction=label.lower())
        if not result:
            continue

        if type == 'Walks Allowed':
            evaluated.append({
                'Pitcher': name,
                'Team': team,
                'Opponent': opp,
                'Prop': type,
                'Line': line,
                'Odds': odds,
                'Direction': label,
                'Season BB/9': result['rules']['season_bb9'],
                'Rolling BB/9 (Last 3 Games)': result['rules']['rolling_bb9'],
                'Opponent BB%': result['rules']['opp_bb_pct'],
                'Median Walks Allowed (Last 3 Games)': result['rules']['median_walks_L3'],
                'Walks Hit Rate': result['rules']['walks_hit_rate'],
                'Rules Hit': result['rule_pass_count'] if 'rule_pass_count' in result else result['rules_hit'] if label == 'Over' else result['rules_miss'],
                'Recommendation': 'Target' if (
                    result['rule_pass_count'] >= 4 if 'rule_pass_count' in result else (
                        result['rules_hit'] >= 4 if label == 'Over' else result['rules_miss'] >= 4
                    )
                ) else 'Pass'
            })
        elif type == 'Pitching Outs':
            evaluated.append({
                'Pitcher': name,
                'Team': team,
                'Opponent': opp,
                'Prop': type,
                'Line': line,
                'Odds': odds,
                'Direction': label,
                'Avg Outs/Start': result['season_outs_per_start'],
                'Rolling Outs/Start (Last 3 Games)': result['rolling_outs3'],
                'Avg Pitch Count (Last 3 Games)': result['avg_pitch_count_3'],
                'Outs Hit Rate': result['outs_hit_rate'],
                'Opponent WHIP vs. Hand': result['opp_whip'],
                'Rules Hit': result['rule_pass_count'] if 'rule_pass_count' in result else result['rules_hit'] if label == 'Over' else result['rules_miss'],
                'Recommendation': 'Target' if (
                    result['rule_pass_count'] >= 4 if 'rule_pass_count' in result else (
                        result['rules_hit'] >= 4 if label == 'Over' else result['rules_miss'] >= 4
                    )
                ) else 'Pass'
            })
        elif type == "Strikeouts":
            evaluated.append({
                'Pitcher': name,
                'Team': team,
                'Opponent': opp,
                'Prop': type,
                'Line': line,
                'Odds': odds,
                'Direction': label,
                'Season K/9': result['rules']['season_k9'],
                'Rolling K/9 (Last 3 Games)': result['rules']['rolling_k9'],
                'Opponent K%': result['rules']['opp_k_pct'],
                'Median Pitch Count (Last 3 Games)': result['rules']['median_pitch_count'],
                'Hit Rate': result['rules']['hit_rate'],
                'Rules Hit': result['rule_pass_count'] if 'rule_pass_count' in result else result['rules_hit'] if label == 'Over' else result['rules_miss'],
                'Recommendation': 'Target' if (
                    result['rule_pass_count'] >= 4 if 'rule_pass_count' in result else (
                        result['rules_hit'] >= 4 if label == 'Over' else result['rules_miss'] >= 4
                    )
                ) else 'Pass'
            })
        else:
            evaluated.append({
                'Pitcher': name,
                'Team': team,
                'Opponent': opp,
                'Prop': type,
                'Line': line,
                'Odds': odds,
                'Direction': label,
                'Season H/9': result['season_h9'],
                'Rolling H/9 (Last 3 Games)': result['rolling_h9'],
                'Opponent AVG vs. Hand': result['opp_avg_vs_hand'],
                'Median Hits Allowed (Last 3 Games)': result['median_hits_allowed'],
                'Hits Allowed Hit Rate': result['ha_hit_rate'],
                'Rules Hit': result['rule_pass_count'] if 'rule_pass_count' in result else result['rules_hit'] if label == 'Over' else result['rules_miss'],
                'Recommendation': 'Target' if (
                    result['rule_pass_count'] >= 4 if 'rule_pass_count' in result else (
                        result['rules_hit'] >= 4 if label == 'Over' else result['rules_miss'] >= 4
                    )
                ) else 'Pass'
            })

final_df = pd.DataFrame(evaluated)
st.dataframe(final_df, use_container_width=True)

if not final_df.empty:
    st.subheader("Top Picks (5/5 Matching Rules)")
    st.dataframe(final_df[final_df['Rules Hit'] == 5], use_container_width=True)

if not final_df.empty:
    st.subheader("Top Picks (4/5 Matching Rules)")
    st.dataframe(final_df[final_df['Rules Hit'] == 4], use_container_width=True)
