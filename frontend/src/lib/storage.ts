/**
 * Đọc ghi localStorage an toàn: trình duyệt chặn lưu trữ (chế độ riêng tư, hết dung lượng)
 * thì không làm vỡ trang, chỉ không giữ được dữ liệu.
 */
export function storageGet(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function storageSet(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Bỏ qua: vẫn dùng được trang, chỉ không lưu.
  }
}
