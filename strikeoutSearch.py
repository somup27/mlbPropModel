import warnings
import requests

warnings.filterwarnings("ignore")

from pybaseball import statcast, playerid_lookup

def get_player_info(mlbam_id):
    url = f'https://statsapi.mlb.com/api/v1/people/{mlbam_id}?hydrate=teams,currentTeam'
    response = requests.get(url)
    data = response.json()

    if 'people' in data and len(data['people']) > 0:
        player = data['people'][0]
        full_name = player.get('fullName')
        position = player.get('primaryPosition', {}).get('name', 'Unknown')
        current_team = player.get('currentTeam', {}).get('name', 'Free Agent or Unknown')
        return {
            'name': full_name,
            'team': current_team,
            'position': position
        }
    else:
        return {'error': 'Player not found'}

# Map Statcast event types to number of outs they generate
EVENT_OUT_VALUES = {
    'strikeout': 1,
    'field_out': 1,
    'force_out': 1,
    'sac_bunt': 1,
    'sac_fly': 1,
    'double_play': 2,
    'grounded_into_double_play': 2,
    'strikeout_double_play': 2,
    'sac_fly_double_play': 2,
    'triple_play': 3,
    'fielders_choice_out': 1
    # All other events are either hits, errors, or non-out plays → 0 outs
}

def compute_total_outs(df):
    """
    Count total outs a pitcher generated in the given Statcast DataFrame.
    Assumes df contains only one pitcher's data.
    """
    out_events = df[df["events"].isin(EVENT_OUT_VALUES)]
    out_counts = out_events["events"].map(EVENT_OUT_VALUES)
    return out_counts.sum()

def compute_innings_pitched(df):
    total_outs = compute_total_outs(df)
    return total_outs / 3

def compute_k9(df):
    strikeouts = len(df[df["events"] == "strikeout"])
    innings_pitched = compute_innings_pitched(df)
    return (strikeouts / innings_pitched) * 9 if innings_pitched > 0 else 0


lines = pitcher_lines_today()
pitchers_today = []
for pitcher in pitchers_today:
    name, opp, k_line, potential_id = line.split(',')
    first_name, last_name = name.split()
    pitchers_today.append((last_name, first_name, opp, float(k_line), potential_id.replace('\n','')))


full_reg_szn = statcast('2025-03-27', '2025-05-04')
full_reg_szn.sort_values(by='game_date', inplace=True)

for pitching_start in pitchers_today:
    last_name, first_name, opp_team, k_line, potential_id = pitching_start
    pitcher_player = potential_id
    if pitcher_player == '':
        id_data = playerid_lookup(last_name, first_name, fuzzy=True)
        if len(id_data) < 1:
            continue
        pitcher_player = id_data['key_mlbam'].iloc[0]
    pitcher_player = int(pitcher_player)
    pitcher_data = full_reg_szn[full_reg_szn['pitcher'] == pitcher_player]
    if len(pitcher_data['game_date'].unique()) >= 3:
        pitcher_data.sort_values(by=['game_date', 'at_bat_number', 'pitch_number'], inplace=True)
        # season_k9
        season_k9 = compute_k9(pitcher_data)
        # rolling_k9
        recent_dates = pitcher_data['game_date'].unique()[-3:]
        recent_pitcher_data = pitcher_data[pitcher_data['game_date'].isin(recent_dates)]
        rolling_k9 = compute_k9(recent_pitcher_data)
        # opponent_kpct_vs_split
        opp_team_df = full_reg_szn[
            (((full_reg_szn['home_team'] == opp_team) & (full_reg_szn['inning_topbot'] == 'Bottom')) | (
                    (full_reg_szn['away_team'] == opp_team) & (full_reg_szn['inning_topbot'] == 'Top')))]
        opp_team_df.sort_values(by=['game_date', 'game_pk', 'at_bat_number', 'pitch_number'], inplace=True)
        opp_team_hand_data = opp_team_df[opp_team_df['p_throws'] == pitcher_data.iloc[0]['p_throws']]
        opponent_kpct_vs_split = len(opp_team_hand_data[opp_team_hand_data['events'] == 'strikeout']) / \
                                     opp_team_hand_data['batter'].astype(int).ne(
                                         opp_team_hand_data['batter'].shift()).sum()
        # median_pitch_count_3
        pitch_counts = recent_pitcher_data.groupby("game_pk").size()
        median_pitch_count_3 = pitch_counts.median()
        # hit_rate
        game_strikeouts = pitcher_data[pitcher_data["events"] == "strikeout"].groupby("game_pk").size()
        hit_games = (game_strikeouts >= k_line).sum()
        total_games = pitcher_data['game_pk'].nunique()
        hit_rate = hit_games / total_games if total_games > 0 else 0
        # park_k_factor (Implement Later)
        rules = [
            season_k9 > 9.0,
            rolling_k9 > 10.0,
            opponent_kpct_vs_split > .24,
            median_pitch_count_3 >= 85,
            hit_rate >= .6
        ]
        player_profile = get_player_info(pitcher_player)
        if sum(rules) >= 4:
            print(f'{first_name} {last_name} ({player_profile["team"]} {player_profile["position"]}) vs. {opp_team} Over {k_line} Strikeouts => {season_k9} K/9, {rolling_k9} L3 K/9, {opponent_kpct_vs_split} Opponent K% vs. Hand, {median_pitch_count_3} L3 Median Pitches Thrown, {hit_rate} Season Hit Rate ({sum(rules)}/5)')




