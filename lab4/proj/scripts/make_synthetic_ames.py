"""ONLY for smoke-testing without Kaggle data. NOT the real Ames dataset.
Usage: python scripts/make_synthetic_ames.py forecast-service/data/ames_train.csv"""
import sys
import numpy as np
import pandas as pd

rng = np.random.default_rng(0)
n = 1460
qual = rng.integers(1, 11, n)
area = rng.normal(1500, 500, n).clip(334, 5000)
bsmt = rng.normal(1050, 400, n).clip(0, 3000)
garage = rng.normal(470, 200, n).clip(0, 1400)
year = rng.integers(1872, 2011, n)
zone = rng.choice(["RL", "RM", "FV", "RH", "C (all)"], n, p=[.79, .15, .045, .01, .005])
price = (-90000 + 55*area + 25*bsmt + 40*garage + 700*(year-1870)
         + 14000*qual + rng.normal(0, 28000, n) * (1 + qual/10)).clip(35000)
df = pd.DataFrame(dict(GrLivArea=area, TotalBsmtSF=bsmt, GarageArea=garage,
                       YearBuilt=year, OverallQual=qual, MSZoning=zone, SalePrice=price))
df.loc[rng.choice(n, 10, replace=False), "GarageArea"] = np.nan  # exercise imputers
df.to_csv(sys.argv[1], index=False)
