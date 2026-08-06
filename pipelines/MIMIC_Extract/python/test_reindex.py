import pandas as pd
import numpy as np

# Create MultiIndex columns
cols1 = pd.MultiIndex.from_tuples([('A', 'mean'), ('B', 'mean'), ('C', 'mean')])
cols2 = pd.MultiIndex.from_tuples([('A', 'mean'), ('C', 'mean')])

df1 = pd.DataFrame(np.random.rand(3, 3), columns=cols1)
df2 = pd.DataFrame(np.random.rand(3, 2), columns=cols2)

print("df2 columns before:")
print(df2.columns)

df2_aligned = df2.reindex(columns=df1.columns)
print("\ndf2 columns after:")
print(df2_aligned.columns)
print("\ndf2 aligned data:")
print(df2_aligned)
