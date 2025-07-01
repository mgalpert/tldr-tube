// Sieve pricing calculations

const PRICING = {
  // YouTube downloader - runs on CPU
  youtubeDownloader: {
    hourlyRate: 0.40, // CPU compute
    avgMinutesPerVideo: 0.5, // Estimate 30 seconds to download
  },
  
  // Pyannote diarization - likely runs on GPU (T4)
  diarization: {
    hourlyRate: 0.81, // T4 GPU
    // Diarization typically processes at ~10x realtime on T4
    processingSpeedMultiplier: 10,
  },
  
  // Our custom isolate_guest function - runs on CPU
  isolateGuest: {
    hourlyRate: 0.40, // CPU compute
    avgMinutesPerVideo: 2, // Estimate 2 minutes for processing
  },
};

export function calculateProcessingCost(videoDurationSeconds: number): {
  breakdown: {
    download: number;
    diarization: number;
    processing: number;
  };
  total: number;
} {
  const videoDurationMinutes = videoDurationSeconds / 60;
  const videoDurationHours = videoDurationMinutes / 60;
  
  // Calculate costs for each step
  const downloadCost = (PRICING.youtubeDownloader.avgMinutesPerVideo / 60) * PRICING.youtubeDownloader.hourlyRate;
  
  // Diarization cost based on actual video duration
  const diarizationTimeHours = videoDurationHours / PRICING.diarization.processingSpeedMultiplier;
  const diarizationCost = diarizationTimeHours * PRICING.diarization.hourlyRate;
  
  // Processing cost
  const processingCost = (PRICING.isolateGuest.avgMinutesPerVideo / 60) * PRICING.isolateGuest.hourlyRate;
  
  return {
    breakdown: {
      download: Number(downloadCost.toFixed(4)),
      diarization: Number(diarizationCost.toFixed(4)),
      processing: Number(processingCost.toFixed(4)),
    },
    total: Number((downloadCost + diarizationCost + processingCost).toFixed(4)),
  };
}

export function formatCost(cost: number): string {
  return `$${cost.toFixed(4)}`;
}

export function formatDuration(seconds: number): string {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = Math.floor(seconds % 60);
  
  if (hours > 0) {
    return `${hours}h ${minutes}m ${secs}s`;
  } else if (minutes > 0) {
    return `${minutes}m ${secs}s`;
  } else {
    return `${secs}s`;
  }
}