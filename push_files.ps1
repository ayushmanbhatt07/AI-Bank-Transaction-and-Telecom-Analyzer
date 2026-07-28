$files = @(
    "README.md",
    "data/anomalous/bank_anomaly.csv",
    "data/anomalous/cdr_anomaly.csv",
    "data/anomalous/ipdr_anomaly.csv",
    "data/clean/bank_final.csv",
    "data/clean/cdr_final.csv",
    "data/clean/ipdr_final.csv",
    "data/ground_truth/anomaly_ground_truth.csv",
    "data/ground_truth/bank_cdr_ground_truth.csv",
    "data/ground_truth/cdr_ipdr_ground_truth.csv",
    "docs/TRI_NETRA_STAGE_WISE_DOCUMENTATION.md",
    "requirements.txt"
)

foreach ($file in $files) {
    if (Test-Path $file) {
        Write-Host "Processing $file..."
        git add $file
        
        $name = Split-Path $file -Leaf
        
        if ($file -eq "README.md") {
            $msg = "Add README.md"
            $desc = "Initialize project documentation structure."
        } elseif ($file -eq "requirements.txt") {
            $msg = "Add requirements.txt"
            $desc = "Initialize project dependencies list."
        } elseif ($file -match "data/anomalous/") {
            $msg = "Add anomalous data file: $name"
            $desc = "Upload anomalous dataset for $name."
        } elseif ($file -match "data/clean/") {
            $msg = "Add clean data file: $name"
            $desc = "Upload clean and preprocessed dataset for $name."
        } elseif ($file -match "data/ground_truth/") {
            $msg = "Add ground truth data file: $name"
            $desc = "Upload ground truth labels for $name."
        } elseif ($file -match "docs/") {
            $msg = "Add documentation file: $name"
            $desc = "Upload detailed project documentation for $name."
        } else {
            $msg = "Add $name"
            $desc = "Commit for $file."
        }

        git commit -m $msg -m $desc
        git push
    } else {
        Write-Host "File $file does not exist, skipping."
    }
}
