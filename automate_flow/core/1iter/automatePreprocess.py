import pandas as pd

### Pulling Information and Safety Checks

file = str(input("emissions.csv (emissions) or tripinfo.csv (tripinfo)?"))

df_emissions = pd.read_csv("csvs\\"+file+".csv", sep=";")

assert file not in ("emissions", "tripinfo"), "Invalid file type"
if file == "emissions": trip = "vehicle_id"
elif file == "tripinfo": trip = "tripinfo_id"

### Helper Functions

def checkMissing(df):
    for f in set(df_emissions["flow_id"].values):
        print("Checking missing values for flow_id",f)

        df_check = df[df["flow_id"] == f]
        
        car_ids = list(sorted(set(df_check["car_id"])))

        missing_ids = [i for i in range(car_ids[0], car_ids[-1] + 1) if i not in car_ids]

        missing_info = [{"missing_id": m,
                        "prev_id": m-1 if m-1 in car_ids else None,
                        "next_id": m+1 if m+1 in car_ids else None} for m in missing_ids]

        print("Missing IDs:", missing_ids)
        print("Details:", missing_info)


def orderSpawn(df):
    # Extract flow number and car number
    df["flow_id"] = df[trip].str.extract(r"flow_(\d+)\.\d+").astype(int)
    df["car_num"] = df[trip].str.split(".", n=1).str[1].astype(int)

    # Sort by flow_id first, then by car_num
    df = df.sort_values(by=["flow_id", "car_num"], ascending=[True, True]).drop(columns=["car_num"])

    return df

def orderSpawn(df):
    # Extract flow number and car number
    df["flow_id"] = df[trip].str.extract(r"flow_(\d+)\.\d+").astype(int)
    df["car_num"] = df[trip].str.split(".", n=1).str[1].astype(int)

    # Sort by flow_id first, then by car_num
    df = df.sort_values(by=["flow_id", "car_num"], ascending=[True, True]).drop(columns=["car_num"])

    return df

### Ordering
    
# Order by ???_id and timestep

# Creates a new column 'car_id' as the integer after the first dot, avoids recurrent flagging
df_emissions["car_id"] = df_emissions[trip].str.split(".", n=1).str[1].astype(int)
df_emissions["flow_id"] = df_emissions[trip].str.extract(r"flow_(\d+)\.\d+").astype(int)

# Sort by car_id and timestep_time
df_emissions = df_emissions.sort_values(by=["flow_id", "car_id", "timestep_time"], ascending=[True, True, True])

checkMissing(df_emissions)

# Group by vehicle_id and compute average CO2 per vehicle
avg_df_emissions = df_emissions.groupby(trip, as_index=False).agg({"vehicle_CO2": "mean"}).rename(columns={"vehicle_CO2": "avg_co2"})
avg_df_emissions.head(20)

avg_df_emissions = orderSpawn(avg_df_emissions)

avg_df_emissions.to_csv("clean_emissions.csv")