import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button.jsx";
import { Badge } from "@/components/ui/badge.jsx";
import { Wifi, WifiOff, RefreshCw, AlertCircle } from "lucide-react";
import { checkBackendHealth } from "../utils/api.js";

const BackendStatus = () => {
  const [status, setStatus] = useState("checking");
  const [lastCheck, setLastCheck] = useState(null);
  const [jobsActive, setJobsActive] = useState(0);
  const [retryCount, setRetryCount] = useState(0);

  const checkStatus = async () => {
    setStatus("checking");
    try {
      const result = await checkBackendHealth();
      if (result.success) {
        setStatus("connected");
        setJobsActive(result.data.jobs_active || 0);
        setRetryCount(0); // Reset retry count on success
      } else {
        setStatus("error");
        setRetryCount((prev) => prev + 1);
      }
    } catch (error) {
      setStatus("error");
      setRetryCount((prev) => prev + 1);
    }
    setLastCheck(new Date());
  };

  useEffect(() => {
    checkStatus();

    // Auto-retry every 30 seconds if there's an error
    const interval = setInterval(() => {
      if (status === "error" && retryCount < 5) {
        checkStatus();
      }
    }, 30000);

    return () => clearInterval(interval);
  }, [status, retryCount]);

  const getStatusColor = () => {
    switch (status) {
      case "connected":
        return "bg-green-500";
      case "error":
        return "bg-red-500";
      case "checking":
        return "bg-yellow-500";
      default:
        return "bg-gray-500";
    }
  };

  const getStatusText = () => {
    switch (status) {
      case "connected":
        return "Connected";
      case "error":
        return "Connection Error";
      case "checking":
        return "Checking...";
      default:
        return "Unknown";
    }
  };

  const getStatusIcon = () => {
    switch (status) {
      case "connected":
        return <Wifi className="w-4 h-4" />;
      case "error":
        return <WifiOff className="w-4 h-4" />;
      case "checking":
        return <RefreshCw className="w-4 h-4 animate-spin" />;
      default:
        return <WifiOff className="w-4 h-4" />;
    }
  };

  return (
    <div className="flex items-center gap-2 text-sm">
      <Badge variant="outline" className="flex items-center gap-1">
        <div className={`w-2 h-2 rounded-full ${getStatusColor()}`} />
        {getStatusIcon()}
        {getStatusText()}
      </Badge>

      {status === "connected" && (
        <span className="text-muted-foreground">{jobsActive} active jobs</span>
      )}

      {status === "error" && (
        <div className="flex items-center gap-1 text-red-500">
          <AlertCircle className="w-3 h-3" />
          <span className="text-xs">Backend not available</span>
        </div>
      )}

      <Button
        variant="ghost"
        size="sm"
        onClick={checkStatus}
        disabled={status === "checking"}
        className="h-6 px-2"
      >
        <RefreshCw
          className={`w-3 h-3 ${status === "checking" ? "animate-spin" : ""}`}
        />
      </Button>

      {lastCheck && (
        <span className="text-xs text-muted-foreground">
          Last check: {lastCheck.toLocaleTimeString()}
        </span>
      )}
    </div>
  );
};

export default BackendStatus;
