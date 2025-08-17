import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button.jsx";
import { Badge } from "@/components/ui/badge.jsx";
import { Wifi, WifiOff, RefreshCw } from "lucide-react";
import { checkBackendHealth } from "../utils/api.js";

const BackendStatus = () => {
  const [status, setStatus] = useState("checking");
  const [lastCheck, setLastCheck] = useState(null);
  const [jobsActive, setJobsActive] = useState(0);

  const checkStatus = async () => {
    setStatus("checking");
    try {
      const result = await checkBackendHealth();
      if (result.success) {
        setStatus("connected");
        setJobsActive(result.data.jobs_active || 0);
      } else {
        setStatus("error");
      }
    } catch (error) {
      setStatus("error");
    }
    setLastCheck(new Date());
  };

  useEffect(() => {
    checkStatus();
  }, []);

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
