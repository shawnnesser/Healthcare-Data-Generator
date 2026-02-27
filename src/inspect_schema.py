import pandas as pd
from sqlalchemy import create_engine
from config import CONNECTION_STRING
engine = create_engine(f"mssql+pyodbc:///?odbc_connect={CONNECTION_STRING}")

for t in ['patients','doctors','encounters']:
    try:
        df = pd.read_sql(f"SELECT TOP 0 * FROM {t}", engine)
        print(t, 'columns:', list(df.columns))
    except Exception as e:
        print('error reading', t, e)
