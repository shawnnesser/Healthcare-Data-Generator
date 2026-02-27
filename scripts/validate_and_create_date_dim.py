from sqlalchemy import create_engine
import sys, os
# ensure src is on path so we can import config and main helpers
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))
from config import CONNECTION_STRING
import pandas as pd

# import date-dim generator from main
from main import generate_date_dimension

engine = create_engine(f'mssql+pyodbc:///?odbc_connect={CONNECTION_STRING}')

def q(sql):
    try:
        return pd.read_sql(sql, engine)
    except Exception as e:
        print('Query error:', e)
        return None

# Get encounter date range
print('Encounters min/max:')
df2 = q('SELECT MIN(encounter_date) as min_d, MAX(encounter_date) as max_d FROM encounters')
if df2 is not None and not pd.isna(df2.iloc[0]['min_d']):
    min_d = pd.to_datetime(df2.iloc[0]['min_d']).date()
    max_d = pd.to_datetime(df2.iloc[0]['max_d']).date()
    print({'min_d': min_d, 'max_d': max_d})
else:
    print('No encounters found or error.')
    min_d = None
    max_d = None

# Ensure date_dim exists and covers the range; create if missing
df_count = q('SELECT COUNT(*) as cnt FROM date_dim')
if df_count is None:
    print('Could not query date_dim (missing). Attempting to create it for encounter range...')
    if min_d and max_d:
        dd = generate_date_dimension(min_d, max_d)
        dd.to_sql('date_dim', engine, if_exists='replace', index=False)
        print('Created date_dim for range', min_d, max_d)
else:
    try:
        print('date_dim rows:', int(df_count.iloc[0]['cnt']))
    except Exception:
        pass

# Show sample rows
print('Sample rows from date_dim (top 5):')
df3 = q('SELECT TOP 5 * FROM date_dim ORDER BY date_key')
if df3 is not None:
    print(df3.head().to_dict(orient='records'))
