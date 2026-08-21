(() => {
  const feedbackDuration = 2500;

  function setTemporaryLabel(button, label) {
    const originalLabel = button.textContent;
    button.textContent = label;
    window.setTimeout(() => {
      button.textContent = originalLabel;
    }, feedbackDuration);
  }

  async function copyShareContent(button) {
    const content = buildShareText(button);
    await navigator.clipboard.writeText(content);
    setTemporaryLabel(button, "Message copié");
  }

  function buildShareText(button) {
    return `${button.dataset.shareText}\n\n${button.dataset.shareUrl}`;
  }

  document.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-invitation-share]");
    if (!button) return;

    const shareData = {
      title: button.dataset.shareTitle,
      text: buildShareText(button),
    };

    button.disabled = true;
    try {
      if (navigator.share) {
        await navigator.share(shareData);
      } else if (navigator.clipboard) {
        await copyShareContent(button);
      } else {
        window.prompt("Copiez ce message d’invitation :", shareData.text);
      }
    } catch (error) {
      if (error.name !== "AbortError") {
        setTemporaryLabel(button, "Partage impossible");
      }
    } finally {
      button.disabled = false;
    }
  });
})();
