def quicksort(arr: list) -> list:
    """Sort a list using QuickSort."""
    if len(arr) <= 1:
        return arr
    pivot = arr[len(arr) // 2]
    left  = [x for x in arr if x < pivot]
    mid   = [x for x in arr if x == pivot]
    right = [x for x in arr if x > pivot]
    return quicksort(left) + mid + quicksort(right)


if __name__ == "__main__":
    print(quicksort([3,1,2]))
