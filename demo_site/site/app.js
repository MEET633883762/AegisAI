"use strict";

const status = document.querySelector("#status");
if (status) {
  fetch("/demo-config.json")
    .then((response) => {
      if (!response.ok) throw new Error("Local demo status unavailable");
      return response.json();
    })
    .then(({ profile }) => {
      status.textContent = `Running locally with the ${profile} profile.`;
    })
    .catch(() => {
      status.textContent = "Running locally; profile status unavailable.";
    });
}
