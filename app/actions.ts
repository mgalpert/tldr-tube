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
