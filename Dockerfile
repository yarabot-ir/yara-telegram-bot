ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG ALL_PROXY

# Use an official Python runtime as the base image
FROM python:3.11

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Setup Proxy If Needed
RUN export http_proxy=${HTTP_PROXY}
RUN export https_proxy=${HTTPS_PROXY}
RUN export all_proxy=${ALL_PROXY}
# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container
COPY . .

# Command to run the bot
CMD ["python", "botcode.py"]
