#!/usr/bin/env python3
"""
XGBoost analysis to identify which parameters in aggregated_screen.csv 
contribute to higher win rates and profit margins
"""

import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.metrics import accuracy_score, mean_squared_error, classification_report
import xgboost as xgb
import matplotlib.pyplot as plt
import seaborn as sns

def load_and_merge_data():
    """Load and merge the screen data with trading results"""
    print("Loading data...")
    
    # Load aggregated screen data
    screen_df = pd.read_csv('../../aggregated_screen.csv')
    print(f"Screen data: {len(screen_df)} rows")
    
    # Load trading results  
    trades_df = pd.read_csv('../../reports/earnings_backtest_2024_09_02_2025_06_30_finviz.csv')
    print(f"Trading data: {len(trades_df)} rows")
    
    # Convert Trade Date to datetime for merging
    screen_df['Trade Date'] = pd.to_datetime(screen_df['Trade Date'])
    trades_df['entry_date'] = pd.to_datetime(trades_df['entry_date'])
    
    # Merge on ticker and date (allowing for some date flexibility)
    merged_data = []
    
    for _, trade in trades_df.iterrows():
        ticker = trade['ticker']
        entry_date = trade['entry_date']
        
        # Find matching screen data within a few days of entry
        screen_matches = screen_df[
            (screen_df['Ticker'] == ticker) & 
            (abs((screen_df['Trade Date'] - entry_date).dt.days) <= 3)
        ]
        
        if len(screen_matches) > 0:
            # Take the closest match
            closest_match = screen_matches.loc[
                (screen_matches['Trade Date'] - entry_date).abs().idxmin()
            ]
            
            # Combine trade and screen data
            combined_row = {
                **trade.to_dict(),
                **closest_match.to_dict()
            }
            merged_data.append(combined_row)
    
    merged_df = pd.DataFrame(merged_data)
    print(f"Merged data: {len(merged_df)} rows")
    
    return merged_df

def prepare_features(df):
    """Prepare features for XGBoost analysis"""
    print("Preparing features...")
    
    # Debug: Print available columns
    print("Available columns in merged data:")
    print([col for col in df.columns if 'RSI' in col or 'Gap' in col or 'Beta' in col])
    
    # Create target variables
    df['is_winner'] = (df['pnl'] > 0).astype(int)
    df['profit_category'] = pd.cut(df['pnl_rate'], 
                                  bins=[-float('inf'), -0.05, 0.05, 0.15, float('inf')],
                                  labels=['Large Loss', 'Small Loss/Gain', 'Good Profit', 'Excellent Profit'])
    
    # Find available numerical features dynamically
    potential_features = [
        'Market Cap', 'P/E', 'Forward P/E', 'PEG', 'P/S', 'P/B', 
        'EPS (ttm)', 'EPS growth this year', 'EPS growth next year',
        'EPS growth past 5 years', 'EPS growth next 5 years',
        'Sales growth past 5 years', 'Return on Assets', 'Return on Equity',
        'Current Ratio', 'Quick Ratio', 'Gross Margin', 'Operating Margin',
        'Profit Margin', 'Performance (Week)', 'Performance (Month)', 
        'Performance (Quarter)', 'Performance (Half Year)', 'Performance (Year)',
        'Beta', 'Volatility (Week)', 'Volatility (Month)', 
        'Relative Strength Index (14)', 'Gap', 'surprise_rate'
    ]
    
    # Only select features that actually exist in the dataframe
    numerical_features = [col for col in potential_features if col in df.columns]
    print(f"Using {len(numerical_features)} features: {numerical_features}")
    
    # Handle missing values and infinite values
    feature_df = df[numerical_features].copy()
    
    # Convert percentage strings to floats
    for col in feature_df.columns:
        if feature_df[col].dtype == 'object':
            # Remove % signs and convert to float
            feature_df[col] = feature_df[col].astype(str).str.replace('%', '').str.replace(',', '')
            feature_df[col] = pd.to_numeric(feature_df[col], errors='coerce')
    
    # Fill missing values with median
    feature_df = feature_df.fillna(feature_df.median())
    
    # Remove infinite values
    feature_df = feature_df.replace([np.inf, -np.inf], np.nan)
    feature_df = feature_df.fillna(feature_df.median())
    
    print(f"Final feature set: {feature_df.shape[1]} features")
    return feature_df, df['is_winner'], df['pnl_rate']

def train_xgboost_models(X, y_class, y_reg):
    """Train XGBoost models for classification and regression"""
    print("Training XGBoost models...")
    
    # Split data
    X_train, X_test, y_class_train, y_class_test, y_reg_train, y_reg_test = train_test_split(
        X, y_class, y_reg, test_size=0.2, random_state=42
    )
    
    # Classification model (win/loss prediction)
    print("Training classification model...")
    clf_model = xgb.XGBClassifier(
        n_estimators=100,
        max_depth=6,
        learning_rate=0.1,
        random_state=42
    )
    clf_model.fit(X_train, y_class_train)
    
    # Predictions and evaluation
    y_class_pred = clf_model.predict(X_test)
    class_accuracy = accuracy_score(y_class_test, y_class_pred)
    print(f"Classification Accuracy: {class_accuracy:.3f}")
    
    # Regression model (profit prediction)
    print("Training regression model...")
    reg_model = xgb.XGBRegressor(
        n_estimators=100,
        max_depth=6,
        learning_rate=0.1,
        random_state=42
    )
    reg_model.fit(X_train, y_reg_train)
    
    # Predictions and evaluation
    y_reg_pred = reg_model.predict(X_test)
    reg_mse = mean_squared_error(y_reg_test, y_reg_pred)
    print(f"Regression MSE: {reg_mse:.4f}")
    
    return clf_model, reg_model, X_train.columns

def analyze_feature_importance(clf_model, reg_model, feature_names):
    """Analyze and visualize feature importance"""
    print("Analyzing feature importance...")
    
    # Get feature importance
    clf_importance = clf_model.feature_importances_
    reg_importance = reg_model.feature_importances_
    
    # Create importance dataframe
    importance_df = pd.DataFrame({
        'feature': feature_names,
        'win_rate_importance': clf_importance,
        'profit_importance': reg_importance
    })
    
    # Sort by average importance
    importance_df['avg_importance'] = (importance_df['win_rate_importance'] + 
                                     importance_df['profit_importance']) / 2
    importance_df = importance_df.sort_values('avg_importance', ascending=False)
    
    print("\n=== TOP 20 MOST IMPORTANT FEATURES ===")
    print(importance_df.head(20).to_string(index=False))
    
    # Create visualization
    plt.figure(figsize=(12, 8))
    
    # Top 15 features for win rate prediction
    plt.subplot(1, 2, 1)
    top_win_features = importance_df.nlargest(15, 'win_rate_importance')
    plt.barh(range(len(top_win_features)), top_win_features['win_rate_importance'])
    plt.yticks(range(len(top_win_features)), top_win_features['feature'])
    plt.xlabel('Importance')
    plt.title('Top Features for Win Rate Prediction')
    plt.gca().invert_yaxis()
    
    # Top 15 features for profit prediction
    plt.subplot(1, 2, 2)
    top_profit_features = importance_df.nlargest(15, 'profit_importance')
    plt.barh(range(len(top_profit_features)), top_profit_features['profit_importance'])
    plt.yticks(range(len(top_profit_features)), top_profit_features['feature'])
    plt.xlabel('Importance')
    plt.title('Top Features for Profit Prediction')
    plt.gca().invert_yaxis()
    
    plt.tight_layout()
    plt.savefig('../../reports/feature_importance_analysis.png', dpi=300, bbox_inches='tight')
    print("\nFeature importance chart saved as '../../reports/feature_importance_analysis.png'")
    
    return importance_df

def generate_insights(importance_df, merged_df):
    """Generate actionable insights from the analysis"""
    print("\n=== KEY INSIGHTS ===")
    
    # Top features for win rate
    top_win_features = importance_df.nlargest(10, 'win_rate_importance')['feature'].tolist()
    print(f"\nTop 10 features for WIN RATE:")
    for i, feature in enumerate(top_win_features, 1):
        print(f"{i}. {feature}")
    
    # Top features for profit
    top_profit_features = importance_df.nlargest(10, 'profit_importance')['feature'].tolist()
    print(f"\nTop 10 features for PROFIT:")
    for i, feature in enumerate(top_profit_features, 1):
        print(f"{i}. {feature}")
    
    # Analyze winners vs losers
    print("\n=== WINNERS VS LOSERS ANALYSIS ===")
    winners = merged_df[merged_df['pnl'] > 0]
    losers = merged_df[merged_df['pnl'] <= 0]
    
    print(f"Winners: {len(winners)} trades")
    print(f"Losers: {len(losers)} trades")
    print(f"Win Rate: {len(winners)/len(merged_df)*100:.1f}%")
    
    # Key differences in top features
    key_features = ['surprise_rate', 'Gap', 'P/E', 'Beta', 'Performance (Week)', 
                   'Performance (Month)', 'Relative Strength Index (14)', 'Volatility (Week)']
    
    for feature in key_features:
        if feature in merged_df.columns:
            try:
                # Convert to numeric if needed - handle concatenated strings
                feature_series = merged_df[feature].astype(str)
                # If it looks like concatenated percentages, take the first value
                if '%' in str(feature_series.iloc[0]) and len(str(feature_series.iloc[0])) > 10:
                    # Extract first percentage value
                    feature_series = feature_series.str.extract(r'(\d+\.?\d*)%')[0]
                else:
                    feature_series = feature_series.str.replace('%', '').str.replace(',', '')
                
                merged_df[feature + '_numeric'] = pd.to_numeric(feature_series, errors='coerce')
                
                winner_mean = winners[feature + '_numeric'].mean()
                loser_mean = losers[feature + '_numeric'].mean()
                
                if not (pd.isna(winner_mean) or pd.isna(loser_mean)):
                    print(f"\n{feature}:")
                    print(f"  Winners avg: {winner_mean:.2f}")
                    print(f"  Losers avg: {loser_mean:.2f}")
                    print(f"  Difference: {winner_mean - loser_mean:.2f}")
            except Exception as e:
                print(f"\nError processing {feature}: {str(e)}")
    
    # Generate recommendations
    print("\n=== RECOMMENDATIONS ===")
    print("Based on feature importance analysis:")
    
    if 'surprise_rate' in top_win_features[:5]:
        print("1. Focus on higher earnings surprise rates")
    if 'Gap' in top_win_features[:5]:
        print("2. Prioritize stocks with significant price gaps")
    if 'Performance (Week)' in top_win_features[:5]:
        print("3. Consider recent weekly performance trends")
    if 'Beta' in top_win_features[:5]:
        print("4. Factor in stock volatility (Beta) for entry decisions")
    if 'P/E' in top_win_features[:5]:
        print("5. Include P/E ratio in screening criteria")

def main():
    """Main analysis function"""
    print("=== XGBOOST FEATURE ANALYSIS ===")
    print("Analyzing which aggregated_screen.csv parameters contribute to trading success\n")
    
    try:
        # Load and merge data
        merged_df = load_and_merge_data()
        
        if len(merged_df) == 0:
            print("ERROR: No matching data found between screen and trades files")
            return
        
        # Prepare features
        X, y_class, y_reg = prepare_features(merged_df)
        
        # Train models
        clf_model, reg_model, feature_names = train_xgboost_models(X, y_class, y_reg)
        
        # Analyze feature importance
        importance_df = analyze_feature_importance(clf_model, reg_model, feature_names)
        
        # Generate insights
        generate_insights(importance_df, merged_df)
        
        print("\n=== ANALYSIS COMPLETE ===")
        
    except Exception as e:
        print(f"ERROR: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()