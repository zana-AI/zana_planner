import pandas as pd

# 1. Read the resolutions file
with open("1403/README.md", "r") as f:
    resolutions = f.readlines()

output_format = "YYYY-MM-DD, Metric, Value"

# 2. Give it to LLM with the following prompt to create the metrics.csv file
prompt = """
    this script takes the resolution file and creates a CSV with intermediate milestones
    if a metric is defined as binary, the value will be 1 or 0, e.g.: sleep before 11pm
    for goals that have a defined deadline, the deadline will be directly added e.g.: apply for job at Google by Sep 2023
    if a resolution is measured in a daily or weekly or monthly basis, create one line for end of each week or month.
"""
prompt += f"output format: {output_format}"
llm_output = ""  # TODO

def call_llm(prompt, input_text):
    # call the LLM API
    pass

with open("metrics.csv", "w") as f:
    f.write(llm_output)

# validate the csv file format
# 1. Check if the file is a csv file
metrics_df = pd.read_csv("metrics.csv")
if metrics_df.columns.tolist() != ["Date", "Metric", "Value"]:
    # TODO: call LLM with explanation
    raise ValueError("The metrics file does not have the correct columns")


# 2. Check if the file has the correct columns


# 3. Check if the file has the correct data types
# 4. Check if the file has the correct data values & ranges



# 3. Make metrics for repetitive tasks accumulative e.g.: read 10 pages "every" day
# the intermediate milestones can use the baseline value provided at the beginning of the year in baselines.csv
# 4. Read the baselines file
# 5. Update the metrics file with the baselines


