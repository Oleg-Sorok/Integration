"""API/database feature naming contract; there is no training code or data here."""
import pandas as pd
API_TO_COLUMN = {
    'gr_liv_area':'GrLivArea', 'total_bsmt_sf':'TotalBsmtSF',
    'garage_area':'GarageArea', 'year_built':'YearBuilt',
    'overall_qual':'OverallQual', 'ms_zoning':'MSZoning',
}
FEATURES = list(API_TO_COLUMN.values())

def to_dataframe(payload):
    return pd.DataFrame([{column: payload[key] for key,column in API_TO_COLUMN.items()}], columns=FEATURES)
