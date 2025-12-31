# Use a stable Python version
FROM python:3.9

# Set the working directory
WORKDIR /app

# Install system dependencies (fixes the "git not found" error if it happens)
RUN apt-get update && apt-get install -y git

# Copy your code into the container
COPY . /app

# Install your Python libraries
RUN pip install --no-cache-dir -r requirements.txt

# Expose the port so Render can see the web server
EXPOSE 10000

# The command to run your bot
CMD ["python", "main.py"]
