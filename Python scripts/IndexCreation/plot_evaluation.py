# plot_results.py
import json
import matplotlib.pyplot as plt
import os

def plot_metrics():
    """
    Loads the k-sweep results and generates plots for Precision, Recall,
    F1-Score, and MRR, saving them as PNG files.
    """
    input_file = 'retrieval_k_sweep_results.json'
    
    if not os.path.exists(input_file):
        print(f"Error: The input file '{input_file}' was not found.")
        print("Please run the evaluation script first to generate the metrics.")
        return

    with open(input_file, 'r') as f:
        data = json.load(f)

    k_values = data['k_values']
    metrics_data = data['metrics']
    
    metrics_to_plot = ['precision', 'recall', 'f1', 'mrr']
    
    # Define display names for professional-looking titles and labels
    metric_display_names = {
        'precision': 'Precision',
        'recall': 'Recall',
        'f1': 'F1-Score',
        'mrr': 'Mean Reciprocal Rank (MRR)'
    }
    
    # Define colors and markers for consistency across plots
    plot_styles = {
        'entity': {'color': 'blue', 'marker': 'o', 'linestyle': '-'},
        'class': {'color': 'green', 'marker': 's', 'linestyle': '--'},
        'property': {'color': 'red', 'marker': '^', 'linestyle': ':'}
    }

    for metric in metrics_to_plot:
        plt.figure(figsize=(10, 6))
        
        for index_name, styles in plot_styles.items():
            # Check if the metric data exists for this index
            if index_name in metrics_data and metric in metrics_data[index_name]:
                plt.plot(
                    k_values, 
                    metrics_data[index_name][metric], 
                    color=styles['color'],
                    marker=styles['marker'],
                    linestyle=styles['linestyle'],
                    label=f'{index_name.capitalize()} Index'
                )

        # Formatting the plot using the display names dictionary
        metric_name_display = metric_display_names.get(metric, metric.capitalize())
        plt.title(f'{metric_name_display}@k for Different Indexes', fontsize=16)
        plt.xlabel('k (Number of Retrieved Documents)', fontsize=12)
        plt.ylabel(f'{metric_name_display} Score', fontsize=12)
        plt.xticks(k_values)
        # Set y-axis to be between 0 and 1 for standard metric representation
        plt.ylim(0, 1.05)
        plt.grid(True, which='both', linestyle='--', linewidth=0.5)
        plt.legend(fontsize=12)
        plt.tight_layout()

        # Save the figure
        output_filename = f'{metric}_at_k_plot.png'
        plt.savefig(output_filename)
        print(f"Successfully generated and saved '{output_filename}'")

if __name__ == '__main__':
    plot_metrics()