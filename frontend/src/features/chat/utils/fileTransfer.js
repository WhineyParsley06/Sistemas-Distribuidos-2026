export const encodeFileAsBase64 = (file) =>
  new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const result = String(reader.result)
      const [, base64] = result.split(',')
      resolve(base64)
    }
    reader.onerror = () => reject(new Error('No se pudo leer el archivo'))
    reader.readAsDataURL(file)
  })

export const downloadBase64File = (file) => {
  const byteChars = atob(file.content)
  const byteNumbers = new Array(byteChars.length)

  for (let i = 0; i < byteChars.length; i += 1) {
    byteNumbers[i] = byteChars.charCodeAt(i)
  }

  const blob = new Blob([new Uint8Array(byteNumbers)], {
    type: file.mimeType || 'application/octet-stream',
  })

  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = file.name
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}
