# -- Imports and Setup --
import streamlit as st
import pandas as pd
import json
from pybaseball import statcast, playerid_lookup
import requests

# ---------------------- Utility Functions ----------------------

@st.cache_data
def pitcher_lines_today():
    kJSON = json.load(open('pitcherLines/strikeoutLines.json', 'r'))
    poJSON = json.load(open('pitcherLines/pitchingOutsLines.json', 'r'))

    pitcher_data = []
    pitcher_keys = []
    for event in kJSON['events']:
        pitcher_keys.append((event['participants'][0]['metadata']['startingPitcherPlayerName'], event['participants'][1]['metadata']['shortName']))
        pitcher_keys.append((event['participants'][1]['metadata']['startingPitcherPlayerName'], event['participants'][0]['metadata']['shortName']))
    pitcher_dict = {pitcher: opponent for pitcher, opponent in pitcher_keys}

    selections = [kJSON, poJSON]
    type = ['Strikeouts', 'Pitching Outs']

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
        rolling_k9 > 10.0,
        opp_k_pct > 0.24,
        median_pitch_count >= 85,
        hit_rate >= 0.6
    ]

    rules_miss = [
        season_k9 < 8.0,
        rolling_k9 < 7.5,
        opp_k_pct < 0.21,
        median_pitch_count < 80,
        hit_rate < 0.4
    ]

    return {
        'rules': rules,
        'rules_hit': sum(rules_hit),
        'rules_miss': sum(rules_miss)
    }


def evaluate_pitching_out_prop(pitcher_data, full_season_data, opp_team, pitching_outs_line, throwing_hand, direction='over'):
    pitcher_data = pitcher_data.sort_values(by=['game_date', 'at_bat_number', 'pitch_number'])

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
    hit_games = (outs_per_game >= pitching_outs_line) if direction == 'over' else (outs_per_game < pitching_outs_line)
    hit_rate = hit_games.sum() / len(outs_per_game) if len(outs_per_game) > 0 else 0


    if direction == 'over':
        rules = [
            season_outs_per_start > pitching_outs_line,
            rolling_outs3 > pitching_outs_line,
            avg_pitch_count_3 >= 90,
            hit_rate >= .6,
            opp_whip <= 1.2
        ]
    else:
        rules = [
            season_outs_per_start < pitching_outs_line,
            rolling_outs3 < pitching_outs_line,
            avg_pitch_count_3 <= 80,
            hit_rate <= .4,
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

# ---------------------- Streamlit UI ----------------------

st.title("MLB Pitcher Props — Rule Evaluation")

with st.spinner("Loading data..."):
    props_df = pitcher_lines_today()
    statcast_df = statcast('2025-03-27', '2025-05-05')

evaluated = []

for _, row in props_df.iterrows():
    name, opp, label, line, odds, type = row['pitcher_name'], row['opponent'], row['label'], row['line'], row['odds'], row['type']
    if opp == "A's": opp = 'ATH'
    if opp == 'ARI': opp = 'AZ'
    if opp == 'WAS': opp = 'WSH'
    pid = get_player_id(name)
    if not pid:
        continue
    pitcher_data = statcast_df[statcast_df['pitcher'] == pid]
    if pitcher_data.empty:
        continue
    hand = pitcher_data['p_throws'].iloc[0]
    profile = get_player_info(pid)
    team = profile['team']

    if type == 'Pitching Outs':
        result = evaluate_pitching_out_prop(pitcher_data, statcast_df, opp, line, hand, direction=label.lower())
    else:
        result = evaluate_pitcher_strikeout_prop(statcast_df, pid, opp, hand, line)

    if not result:
        continue

    if type == 'Pitching Outs':
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
    else:
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


final_df = pd.DataFrame(evaluated)
st.dataframe(final_df, use_container_width=True)

if not final_df.empty:
    st.subheader("Top Picks (≥4 Matching Rules)")
    st.dataframe(final_df[final_df['Recommendation'] == 'Target'], use_container_width=True)
