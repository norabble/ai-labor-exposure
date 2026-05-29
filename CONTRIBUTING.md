# Contribution Guidelines

## Coding Standards

### Variable Naming

We adhere to a high standard of descriptive and clear variable naming to ensure code readability and maintainability across the project.

**Rules:**

1. **Avoid Generic Abbreviations:** Do not use generic abbreviations like `df`, `res`, `tmp`, `val`, `z`, or `f`. Instead, describe what the variable represents.
   - *Bad:* `df = pd.read_csv(...)`
   - *Good:* `occupation_exposure_df = pd.read_csv(...)`

2. **Be Specific:** If you have multiple similar data structures, use descriptive prefixes or suffixes to differentiate them.
   - *Bad:* `path_22`, `path_23`, `df1`, `df2`
   - *Good:* `bls_data_path_2022`, `bls_data_path_2023`, `bls_data_2022`, `bls_data_2023`

3. **Domain Terminology:** Use terminology that matches the domain (e.g., `penetration_value`, `demand_type`, `onet_tasks_df`).
   - *Bad:* `p = row["penetration"]`, `d = row["Demand Type"]`
   - *Good:* `penetration_value = row["penetration"]`, `demand_type = row["Demand Type"]`

4. **Self-Documenting Code:** The name of the variable should explain what it contains without needing a comment.
   - *Bad:* `agg = ... # Aggregate by occupation`
   - *Good:* `occupation_aggregation_df = ...`

### File Documentation

Every Python file should contain a module-level docstring at the very top explaining:
1. The file's name.
2. A high-level description of what the file does.
3. Any core logic, inputs, and outputs if applicable.

This is especially important for files with abbreviated or somewhat cryptic names (e.g., `analyze_bls.py`).
