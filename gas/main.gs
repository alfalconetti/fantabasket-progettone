// Fantabasket — Web App GAS
// doPost principale che smista alle varie azioni

function doPost(e) {
  try {
    const payload = JSON.parse(e.postData.contents);

    // Auth check
    const token = PropertiesService.getScriptProperties().getProperty('AUTH_TOKEN');
    if (payload.token !== token) {
      return respond({ error: "Unauthorized" }, 401);
    }

    switch (payload.action) {
      case "roster":  return handleRoster(payload);
      case "scelte":  return handleScelte(payload);
      default:        return respond({ error: "Unknown action: " + payload.action });
    }

  } catch (err) {
    return respond({ error: err.message, stack: err.stack });
  }
}

function respond(data) {
  return ContentService
    .createTextOutput(JSON.stringify(data))
    .setMimeType(ContentService.MimeType.JSON);
}
