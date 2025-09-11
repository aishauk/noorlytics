#!/bin/bash

echo "🔧 Setting up Noorlytics environment..."

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt

# Bonus: Install Ollama CLI if not already installed
if ! command -v ollama &> /dev/null; then
  echo "📦 Installing Ollama..."
  brew install ollama
fi

echo "✅ Setup complete. Run 'source venv/bin/activate' to activate environment."

#chmod +x setup_noorlytics.sh
#./setup_noorlytics.sh