from sqlalchemy import create_engine
import sys, os
# ensure src is on path so we can import config
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))
from config import CONNECTION_STRING
import pandas as pd

engine = create_engine(f'mssql+pyodbc:///?odbc_connect={CONNECTION_STRING}')

def q(sql):
    try:
        return pd.read_sql(sql, engine)
    except Exception as e:
        print('Query error:', e)
        return None

print('Date dimension count:')
df = q('SELECT COUNT(*) as cnt FROM date_dim')
if df is not None:
    print(df.iloc[0]['cnt'])

print('Encounters min/max:')
df2 = q('SELECT MIN(encounter_date) as min_d, MAX(encounter_date) as max_d FROM encounters')
if df2 is not None:
    print(df2.iloc[0].to_dict())

print('Sample rows from date_dim (top 5):')
df3 = q('SELECT TOP 5 * FROM date_dim ORDER BY date_key')
if df3 is not None:
    print(df3.head().to_dict(orient='records'))
