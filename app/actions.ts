"use server";

const api_key = process.env.SIEVE_KEY;

export const getJobStatus = async (jobId: string) => {
  const endpoint = `https://mango.sievedata.com/v2/jobs/${jobId}`;
  if (!api_key) return;

  const headers = {
    "X-API-Key": api_key,
  };

  const response = await fetch(endpoint, { headers });
  const data = await response.json();
  console.log("Job status:", data.status);
  if (data.status === "error") {
    console.error("Job error details:", data.error);
  }
  return data;
};

export const submitVideo = async (
  videoUrl: string,
  mode: string
): Promise<string | undefined> => {
  if (!api_key) return;
  console.log("fetching video");

  const result = await fetch("https://mango.sievedata.com/v2/push", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": api_key,
    },
    body: JSON.stringify({
      function: "sieve-demos/create-tldr-video",
      inputs: {
        youtube_video_url: videoUrl,
        mode: mode,
        adhd_level: "normal",
      },
    }),
  });

  const resultJson = await result.json();
  const jobId = resultJson.id;
  return jobId;
};

export const isolateGuest = async (
  videoUrl: string
): Promise<string | undefined> => {
  if (!api_key) {
    console.error("No API key found");
    return;
  }
  console.log("isolating guest from podcast video:", videoUrl);

  try {
    const result = await fetch("https://mango.sievedata.com/v2/push", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-API-Key": api_key,
      },
      body: JSON.stringify({
        function: "msg-containsmsg-com/isolate-podcast-guest",
        inputs: {
          youtube_video_url: videoUrl,
        },
      }),
    });

    const resultJson = await result.json();
    console.log("Sieve API response:", resultJson);
    
    if (!result.ok) {
      console.error("Sieve API error:", resultJson);
      return;
    }
    
    const jobId = resultJson.id;
    return jobId;
  } catch (error) {
    console.error("Error calling Sieve API:", error);
    return;
  }
};
