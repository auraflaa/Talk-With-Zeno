#!/bin/bash
# Start Talk With Zeno Locally
# This script starts both backend and frontend servers

echo ""
echo "=== Starting Talk With Zeno Locally ==="
echo ""

# Get local IP address
LOCAL_IP=$(hostname -I | awk '{print $1}')

if [ -z "$LOCAL_IP" ]; then
    LOCAL_IP="localhost"
fi

echo "Local IP: $LOCAL_IP"
echo ""
echo "Starting servers..."
echo ""

# Check if .env.local exists
if [ ! -f ".env.local" ]; then
    echo "Warning: .env.local not found!"
    echo "Please create .env.local from .env.example"
    echo ""
fi

# Start backend in background
echo "Starting Backend on http://0.0.0.0:5000..."
python backend/run.py &
BACKEND_PID=$!

# Wait for backend to start
sleep 3

# Start frontend
echo "Starting Frontend on http://0.0.0.0:3000..."
npm run dev &
FRONTEND_PID=$!

# Wait a bit
sleep 2

echo ""
echo "=== Servers Started ==="
echo ""
echo "Frontend URLs:"
echo "  Local:  http://localhost:3000"
echo "  Network: http://$LOCAL_IP:3000"
echo ""
echo "Backend URLs:"
echo "  Local:  http://localhost:5000"
echo "  Network: http://$LOCAL_IP:5000"
echo ""
echo "Share the Network URL with others on your local network!"
echo ""
echo "Press Ctrl+C to stop servers"
echo ""

# Wait for user interrupt
trap "kill $BACKEND_PID $FRONTEND_PID; exit" INT TERM
wait

