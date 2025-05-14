import React from "react";

const PurpleGradientBackground: React.FC = () => {
  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: -10,
        overflow: "hidden",
      }}
    >
      {/* Radial gradient background from light purple to transparent */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          background:
            "radial-gradient(ellipse at 50% 120%, rgba(168, 85, 247, 0.6), transparent 50%)",
          backgroundSize: "200% 100%", // makes it oblong horizontally
          backgroundRepeat: "no-repeat",
        }}
      />
    </div>
  );
};

export default PurpleGradientBackground;
